"""Tests for WEB-1, WEB-2 and WEB-3 in docs/specs.md.

`app.main` reads its settings at import, so each test imports it in a fresh
Python process. The test client is used without its context manager, so the
lifespan (the background worker) does not start.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

CLIENT_CODE = """
import json
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
root = c.get("/")
tags = c.get("/api/tags")
print(json.dumps({
    "root_status": root.status_code,
    "root_body": root.text,
    "root_type": root.headers.get("content-type", ""),
    "tags_status": tags.status_code,
    "tags_json": tags.json(),
}))
"""


def _client(tmp_path: Path, dist: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("YT_TRANSCRIPTS_")}
    env["YT_TRANSCRIPTS_DATA_DIR"] = str(tmp_path / "data")
    env["YT_TRANSCRIPTS_FRONTEND_DIST"] = str(dist)
    out = subprocess.run(
        [sys.executable, "-c", CLIENT_CODE],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_web1_web2_serves_built_frontend_and_api(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>yt-frontend-marker</html>", encoding="utf-8")
    got = _client(tmp_path, dist)
    assert got["root_status"] == 200
    assert "yt-frontend-marker" in got["root_body"]
    assert got["root_type"].startswith("text/html")
    assert got["tags_status"] == 200
    assert "tags" in got["tags_json"]


def test_web3_api_only_without_built_frontend(tmp_path):
    got = _client(tmp_path, tmp_path / "missing-dist")
    assert got["root_status"] == 404
    assert got["tags_status"] == 200
