"""faster-whisper transcription wrapper.

Loads the model lazily on first use and keeps it in memory for the
lifetime of the process.

Device selection is best-effort with a CPU safety net:
1. If `torch.cuda.is_available()` reports True, try `cuda` + `float16`.
2. If that load fails for any reason (driver glitch, OOM, mismatched
   CTranslate2 CUDA libs, etc.), fall back to `cpu` + `int8`.
3. If CUDA was never available, go straight to CPU.

CPU transcription works but is much slower — expect ~real-time playback
speed on `medium`. The summary log line at startup tells you which path
was actually taken.

Long audio is transcribed in parts (TR-1 to TR-3 in docs/specs.md).
faster-whisper builds the features for all the audio it is given at once,
about 45 MB a minute, so one call on a long video can use more memory than
the model itself. ffmpeg decodes the audio to a temporary file of 16 kHz
float32 samples, which is read through a memory map, and Whisper gets at
most PART_SECONDS of it at a time, cut at a quiet moment.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import torch
from faster_whisper import WhisperModel

from .paths import TRANSCRIPTS_DIR


log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# Longest part given to Whisper in one call (TR-2).
PART_SECONDS = 10 * 60
# Each cut is at the quietest window in this many seconds before the limit.
SEARCH_SECONDS = 30
WINDOW_SECONDS = 0.5


_model: Optional[WhisperModel] = None
_model_name: str = os.environ.get("YT_TRANSCRIPTS_WHISPER_MODEL") or "medium"


def _try_load(device: str, compute_type: str) -> WhisperModel:
    log.info(
        "Loading Whisper model %r on %s (%s)…", _model_name, device, compute_type
    )
    return WhisperModel(_model_name, device=device, compute_type=compute_type)


def get_model() -> WhisperModel:
    global _model
    if _model is not None:
        return _model

    if torch.cuda.is_available():
        try:
            _model = _try_load("cuda", "float16")
            return _model
        except Exception as exc:  # noqa: BLE001 — any CUDA load failure → CPU
            log.warning(
                "CUDA detected but Whisper failed to load on GPU: %s. "
                "Falling back to CPU (transcription will be much slower).",
                exc,
            )

    _model = _try_load("cpu", "int8")
    return _model


def decode(audio_path: Path, out_path: Path) -> np.memmap:
    """Decode the audio with ffmpeg to 16 kHz mono float32 samples in
    `out_path`, and return them as a read-only memory map (TR-1)."""
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(audio_path),
            "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", str(out_path),
        ],
        check=True,
        capture_output=True,
    )
    return np.memmap(out_path, dtype=np.float32, mode="r")


def split_parts(
    samples: np.ndarray, part: int, search: int, window: int
) -> list[tuple[int, int]]:
    """Return (start, end) sample ranges of at most `part` samples that
    cover `samples` in order. Each cut is in the middle of the quietest
    `window` in the `search` samples before the limit (TR-2)."""
    total = len(samples)
    parts: list[tuple[int, int]] = []
    start = 0
    while total - start > part:
        lo = start + part - search
        region = np.asarray(samples[lo : start + part], dtype=np.float32)
        count = len(region) // window
        energy = np.square(region[: count * window]).reshape(count, window).sum(axis=1)
        cut = lo + int(np.argmin(energy)) * window + window // 2
        parts.append((start, cut))
        start = cut
    parts.append((start, total))
    return parts


def transcribe(
    audio_path: Path,
    on_progress: Callable[[float, str], None],
    language: str = "en",
) -> Path:
    """Transcribe the audio file. Saves the raw transcript in TRANSCRIPTS_DIR.

    Skips work entirely if the raw transcript already exists for this audio
    file. Returns the path to the raw transcript file.
    """
    out_path = TRANSCRIPTS_DIR / f"{audio_path.stem}.raw.txt"
    if out_path.exists() and out_path.stat().st_size > 0:
        on_progress(100.0, f"Using cached transcript ({out_path.name})")
        return out_path

    model = get_model()
    on_progress(0.0, "Transcribing 0%")
    lang: Optional[str] = None if language == "auto" else language

    with tempfile.TemporaryDirectory(prefix="yt-transcribe-") as tmp:
        samples = decode(audio_path, Path(tmp) / "audio.f32")
        total = len(samples)
        parts = split_parts(
            samples,
            part=int(PART_SECONDS * SAMPLE_RATE),
            search=int(SEARCH_SECONDS * SAMPLE_RATE),
            window=int(WINDOW_SECONDS * SAMPLE_RATE),
        )
        if len(parts) > 1:
            log.info(
                "Transcribing %.0f s of audio in %d parts", total / SAMPLE_RATE, len(parts)
            )
        pieces: list[str] = []
        pct = 0.0
        count = 0
        for start, end in parts:
            # A copy, so the memory map can close when the folder goes.
            audio = np.array(samples[start:end], dtype=np.float32)
            segments_iter, info = model.transcribe(audio, language=lang, beam_size=5)
            if lang is None:
                lang = info.language
            for segment in segments_iter:
                pieces.append(segment.text.strip())
                if total > 0:
                    done = start + segment.end * SAMPLE_RATE
                    pct = max(pct, min(99.0, done / total * 100.0))
                if count % 5 == 0:
                    on_progress(pct, f"Transcribing {pct:.0f}%")
                count += 1
            del audio
        del samples

    raw_text = " ".join(p for p in pieces if p).strip()
    out_path.write_text(raw_text, encoding="utf-8")
    on_progress(100.0, "Transcription complete")
    return out_path
