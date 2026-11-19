"""yt-dlp wrapper that downloads audio and emits progress to a callback."""

from pathlib import Path
from typing import Callable

import yt_dlp

from .paths import AUDIO_DIR


# Single output template — id is unique per video, safer than title for filesystems.
OUTPUT_TEMPLATE = str(AUDIO_DIR / "%(id)s.%(ext)s")

# Prefer the AAC/m4a audio-only stream (no re-encode needed and ~10× smaller
# than YouTube's high-bitrate Opus/.webm). Falls back to whatever bestaudio is
# if m4a isn't offered for a given video.
FORMAT_SELECTOR = "bestaudio[ext=m4a]/bestaudio"

# YouTube serves audio only to clients that solve its JavaScript challenges.
# yt-dlp runs the EJS solver scripts (the yt-dlp-ejs package) in an external
# runtime and enables only Deno by default; the server has Node. Without a
# runtime the download fails with HTTP 403.
JS_RUNTIMES = {"deno": {}, "node": {}}


def download_audio(
    url: str,
    on_progress: Callable[[float, str], None],
) -> tuple[Path, str]:
    """Download audio for a YouTube URL.

    Skips the download entirely if a cached audio file already exists for
    this video id. Returns (audio_path, video_title).

    on_progress is called with (percent_0_to_100, label).
    """
    # Probe metadata first to learn the video id without downloading bytes.
    on_progress(0.0, "Resolving video…")
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "js_runtimes": JS_RUNTIMES}) as probe:
        info = probe.extract_info(url, download=False)

    video_id = info.get("id", "unknown")
    title = info.get("title", "Untitled")

    cached = _resolve_final_path(video_id)
    if cached is not None:
        on_progress(100.0, f"Using cached audio ({cached.name})")
        return cached, title

    # No cache — fetch the audio stream.
    final_path: dict[str, str] = {}

    def progress_hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100.0) if total else 0.0
            speed = d.get("speed") or 0
            speed_mb = speed / (1024 * 1024) if speed else 0
            on_progress(pct, f"Downloading {pct:.1f}% ({speed_mb:.1f} MB/s)")
        elif status == "finished":
            final_path["path"] = d.get("filename", "")
            on_progress(100.0, "Download complete")

    ydl_opts = {
        "format": FORMAT_SELECTOR,
        "js_runtimes": JS_RUNTIMES,
        "outtmpl": OUTPUT_TEMPLATE,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,  # we use the hook instead
        # No postprocessor: the m4a stream is already in the final form Whisper
        # can consume. If the fallback to non-m4a triggers, faster-whisper /
        # ffmpeg can still read whatever container yt-dlp produced.
        "overwrites": False,
        "continuedl": True,  # resume partial downloads
        # Resilience: retry network and extractor errors with internal backoff
        "retries": 10,              # whole-download retries
        "fragment_retries": 10,     # per-fragment for HLS/DASH
        "extractor_retries": 5,     # YouTube extractor errors
        "socket_timeout": 30,       # per-socket op
        "retry_sleep_functions": {  # internal exponential backoff
            "http": lambda n: min(2 ** n, 60),
            "fragment": lambda n: min(2 ** n, 60),
            "extractor": lambda n: min(2 ** n, 60),
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    audio_path = _resolve_final_path(video_id)
    if audio_path is None:
        # Last-resort fallback to whatever the progress hook captured
        audio_path = Path(final_path.get("path", ""))
    return audio_path, title


def _resolve_final_path(video_id: str) -> Path | None:
    """Find the audio file by video id. Prefers .m4a, then anything else."""
    matches = list(AUDIO_DIR.glob(f"{video_id}.*"))
    if not matches:
        return None
    matches.sort(key=lambda p: (p.suffix != ".m4a", p.name))
    return matches[0]
