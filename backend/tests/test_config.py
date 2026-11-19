"""Tests for CFG-1 and CFG-2 in docs/specs.md.

The settings are read when the modules are imported, so each test imports
them in a fresh Python process with the environment it needs.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _run(code: str, **env: str) -> dict:
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("YT_TRANSCRIPTS_")}
    full_env.update(env)
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=full_env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


PATHS_CODE = (
    "import json; from app import paths, db; "
    "print(json.dumps({'data': str(paths.DATA_DIR), 'audio': str(paths.AUDIO_DIR), "
    "'transcripts': str(paths.TRANSCRIPTS_DIR), 'db': str(db.DB_PATH)}))"
)


def test_cfg1_data_dir_from_environment(tmp_path):
    target = tmp_path / "state"
    got = _run(PATHS_CODE, YT_TRANSCRIPTS_DATA_DIR=str(target))
    assert Path(got["data"]) == target
    assert Path(got["audio"]) == target / "audio"
    assert Path(got["transcripts"]) == target / "transcripts"
    assert Path(got["db"]) == target / "jobs.db"
    assert (target / "audio").is_dir()
    assert (target / "transcripts").is_dir()


def test_cfg1_data_dir_default():
    # Imports only `paths`, so the test does not open the real jobs.db.
    got = _run("import json; from app import paths; print(json.dumps({'data': str(paths.DATA_DIR)}))")
    assert Path(got["data"]) == REPO_ROOT / "data"


MODEL_CODE = "import json; from app import transcriber; print(json.dumps({'model': transcriber._model_name}))"


def test_cfg2_whisper_model_from_environment():
    got = _run(MODEL_CODE, YT_TRANSCRIPTS_WHISPER_MODEL="small")
    assert got["model"] == "small"


def test_cfg2_whisper_model_default():
    got = _run(MODEL_CODE)
    assert got["model"] == "medium"
