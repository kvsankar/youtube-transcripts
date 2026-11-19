"""DL-1: yt-dlp must solve YouTube's JavaScript challenges.

Without a JavaScript runtime and the EJS challenge scripts, YouTube answers the
audio download with HTTP 403. Node is the runtime installed on the server, and
yt-dlp enables only Deno unless told otherwise.
"""

import importlib.util

from app import downloader


class _FakeYDL:
    calls: list[dict] = []

    def __init__(self, opts):
        self.opts = opts
        _FakeYDL.calls.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return {"id": "vid123", "title": "A video"}

    def download(self, urls):
        return 0


def test_every_yt_dlp_call_enables_node_and_deno(monkeypatch, tmp_path):
    _FakeYDL.calls = []
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", _FakeYDL)
    monkeypatch.setattr(downloader, "AUDIO_DIR", tmp_path)

    downloader.download_audio("https://www.youtube.com/watch?v=vid123", lambda p, l: None)

    assert len(_FakeYDL.calls) == 2  # the metadata probe and the download
    for opts in _FakeYDL.calls:
        runtimes = opts.get("js_runtimes", {})
        assert "node" in runtimes and "deno" in runtimes


def test_ejs_challenge_scripts_are_installed():
    assert importlib.util.find_spec("yt_dlp_ejs") is not None
