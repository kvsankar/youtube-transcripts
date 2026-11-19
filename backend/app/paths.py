"""Resolved paths for the project's runtime data directories.

All runtime artifacts (downloaded audio, transcripts, SQLite db) live under
one data directory: `YT_TRANSCRIPTS_DATA_DIR` when it is set, otherwise
`data/` at the project root. A complete state wipe is then a one-line
`rm -rf` of that directory.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.environ.get("YT_TRANSCRIPTS_DATA_DIR") or PROJECT_ROOT / "data")
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
