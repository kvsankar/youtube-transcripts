"""Make the `app` package importable for in-process tests, with a scratch data dir."""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# app.paths creates its folders on import; keep them out of the checkout.
os.environ.setdefault("YT_TRANSCRIPTS_DATA_DIR", tempfile.mkdtemp(prefix="yt-transcripts-test-"))
