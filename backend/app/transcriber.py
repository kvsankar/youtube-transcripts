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
"""

import logging
import os
from pathlib import Path
from typing import Callable, Optional

import torch
from faster_whisper import WhisperModel

from .paths import TRANSCRIPTS_DIR


log = logging.getLogger(__name__)


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


def transcribe(
    audio_path: Path,
    on_progress: Callable[[float, str], None],
    language: str = "en",
) -> Path:
    """Transcribe the audio file. Saves raw transcript next to the audio.

    Skips work entirely if the raw transcript already exists for this audio
    file. Returns the path to the raw transcript file.
    """
    out_path = TRANSCRIPTS_DIR / f"{audio_path.stem}.raw.txt"
    if out_path.exists() and out_path.stat().st_size > 0:
        on_progress(100.0, f"Using cached transcript ({out_path.name})")
        return out_path

    model = get_model()
    on_progress(0.0, "Transcribing 0%")

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=None if language == "auto" else language,
        beam_size=5,
    )

    duration = info.duration or 0.0
    pieces: list[str] = []
    for i, segment in enumerate(segments_iter):
        pieces.append(segment.text.strip())
        if duration > 0:
            pct = min(99.0, segment.end / duration * 100.0)
        else:
            pct = 0.0
        if i % 5 == 0:
            on_progress(pct, f"Transcribing {pct:.0f}%")

    raw_text = " ".join(pieces).strip()
    out_path.write_text(raw_text, encoding="utf-8")
    on_progress(100.0, "Transcription complete")
    return out_path
