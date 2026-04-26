"""Resolved paths for the project's runtime data directories.

All runtime artifacts (downloaded audio, transcripts, SQLite db) live under
a single `data/` directory at the project root. This keeps the repo clean
and makes a complete state wipe a one-line `rm -rf data`.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
