"""Tests for TR-1 to TR-3 in docs/specs.md (transcription in parts)."""

import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from app import transcriber


def _loud(n: int) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.uniform(-0.5, 0.5, n).astype(np.float32)


def test_tr2_cuts_at_the_quietest_window():
    samples = _loud(2500)
    samples[950:960] = 0.0
    samples[1895:1905] = 0.0

    parts = transcriber.split_parts(samples, part=1000, search=200, window=10)

    assert parts == [(0, 955), (955, 1900), (1900, 2500)]


def test_tr2_parts_cover_the_audio_and_stay_under_the_limit():
    samples = _loud(10_007)

    parts = transcriber.split_parts(samples, part=1000, search=200, window=10)

    assert parts[0][0] == 0 and parts[-1][1] == len(samples)
    for (_, end), (start, _) in zip(parts, parts[1:]):
        assert end == start
    assert all(0 < e - s <= 1000 for s, e in parts)


def test_tr2_short_audio_is_one_part():
    assert transcriber.split_parts(_loud(500), part=1000, search=200, window=10) == [(0, 500)]


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, language=None, beam_size=5):
        self.calls.append((len(audio), language))
        n = len(self.calls)
        seconds = len(audio) / transcriber.SAMPLE_RATE
        segments = [
            SimpleNamespace(text=f" part{n}a ", end=seconds / 2),
            SimpleNamespace(text=f"part{n}b", end=seconds),
        ]
        return iter(segments), SimpleNamespace(language="de", duration=seconds)


def test_tr3_parts_are_joined_in_order(tmp_path, monkeypatch):
    rate = transcriber.SAMPLE_RATE
    samples = _loud(rate * 25)  # 25 seconds, parts of 10 seconds
    model = FakeModel()
    monkeypatch.setattr(transcriber, "TRANSCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(transcriber, "get_model", lambda: model)
    monkeypatch.setattr(transcriber, "decode", lambda path, out: samples)
    monkeypatch.setattr(transcriber, "PART_SECONDS", 10)
    monkeypatch.setattr(transcriber, "SEARCH_SECONDS", 2)
    progress = []

    out = transcriber.transcribe(
        tmp_path / "vid.m4a", lambda pct, label: progress.append(pct), language="auto"
    )

    assert out.read_text() == "part1a part1b part2a part2b part3a part3b"
    assert len(model.calls) == 3
    assert all(n <= 10 * rate for n, _ in model.calls)
    assert sum(n for n, _ in model.calls) == len(samples)
    assert [lang for _, lang in model.calls] == [None, "de", "de"]
    assert progress == sorted(progress) and progress[-1] == 100.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_tr1_decode_reads_samples_from_a_file(tmp_path):
    src = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:sample_rate=44100:duration=2", "-ac", "2", str(src)],
        check=True,
    )

    samples = transcriber.decode(src, tmp_path / "tone.f32")

    assert isinstance(samples, np.memmap)
    assert samples.dtype == np.float32
    assert abs(len(samples) - 2 * transcriber.SAMPLE_RATE) <= 160
    # ffmpeg's sine source has amplitude 1/8; int16 samples would read far above 1.
    assert 0.1 < float(np.abs(samples).max()) <= 1.0
