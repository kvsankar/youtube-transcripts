"""faster-whisper transcription wrapper.

Loads the model lazily on first use and keeps it on the GPU for the
lifetime of the process.
"""

from pathlib import Path
from typing import Callable, Optional

import torch
from faster_whisper import WhisperModel

from .paths import TRANSCRIPTS_DIR


_model: Optional[WhisperModel] = None
_model_name: str = "medium"


def _device_and_compute() -> tuple[str, str]:
    if torch.cuda.is_available():
        return "cuda", "float16"
    return "cpu", "int8"


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        device, compute_type = _device_and_compute()
        _model = WhisperModel(_model_name, device=device, compute_type=compute_type)
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
        # Throttle event noise: every 5 segments
        if i % 5 == 0:
            on_progress(pct, f"Transcribing {pct:.0f}%")

    raw_text = " ".join(pieces).strip()
    out_path.write_text(raw_text, encoding="utf-8")
    on_progress(100.0, "Transcription complete")
    return out_path
