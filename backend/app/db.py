"""SQLite connection + schema for the jobs table.

Uses WAL mode for concurrent read/write and `isolation_level=None` for
autocommit. SQLite is plenty fast for our write rate (~10/s during a
running job) and gives us free persistence across restarts.
"""

import sqlite3
from pathlib import Path

from .paths import DATA_DIR

DB_PATH: Path = DATA_DIR / "jobs.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
        isolation_level=None,  # autocommit
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0,
            stage_label TEXT NOT NULL DEFAULT 'Queued',
            title TEXT,
            audio_path TEXT,
            raw_transcript_path TEXT,
            structured_transcript_path TEXT,
            summary_path TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)")
    # Migrations for older databases
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "summary_path" not in existing_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN summary_path TEXT")
    if "tags" not in existing_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
