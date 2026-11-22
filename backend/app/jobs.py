"""Job model and SQLite-backed job store with async event broadcasting.

The store keeps two pieces of state:
- jobs: persisted in SQLite (`jobs.db` at the project root)
- subscribers: in-memory asyncio.Queues that receive lifecycle events for SSE
"""

import asyncio
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Iterable, Literal, Optional

from . import db


log = logging.getLogger(__name__)


JobStatus = Literal[
    "queued",
    "downloading",
    "transcribing",
    "structuring",
    "summarizing",
    "done",
    "failed",
    "cancelled",
]

ACTIVE_STATUSES: tuple[JobStatus, ...] = (
    "downloading",
    "transcribing",
    "structuring",
    "summarizing",
)


@dataclass
class Job:
    id: str
    url: str
    status: JobStatus = "queued"
    progress: float = 0.0
    stage_label: str = "Queued"
    title: Optional[str] = None
    audio_path: Optional[str] = None
    raw_transcript_path: Optional[str] = None
    structured_transcript_path: Optional[str] = None
    summary_path: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    # How many times a restart put this job back in the queue (JOB-2).
    restarts: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Job":
        data = {k: row[k] for k in row.keys()}
        raw_tags = data.get("tags")
        if isinstance(raw_tags, str):
            try:
                data["tags"] = json.loads(raw_tags)
            except json.JSONDecodeError:
                data["tags"] = []
        elif raw_tags is None:
            data["tags"] = []
        return cls(**data)


# Columns in canonical insert order. `tags` is JSON-encoded on the way in
# and decoded on the way out by Job.from_row.
_COLUMNS = (
    "id", "url", "status", "progress", "stage_label",
    "title", "audio_path", "raw_transcript_path", "structured_transcript_path",
    "summary_path", "error", "created_at", "updated_at", "tags", "restarts",
)

# A restart puts an interrupted job back in the queue this many times (JOB-2).
MAX_RESTARTS = 1

# The error prefix of each running status; the frontend marks the failed step
# by this prefix.
_ERROR_PREFIX: dict[str, str] = {
    "downloading": "Download failed",
    "transcribing": "Transcription failed",
    "structuring": "Structuring failed",
    "summarizing": "Summarization failed",
}

# Columns whose value passes through json.dumps before hitting SQLite
_JSON_COLUMNS = {"tags"}


def _encode_for_db(col: str, value):
    if col in _JSON_COLUMNS:
        return json.dumps(value)
    return value


def _completeness(job: Job) -> int:
    """Higher = more pipeline output exists. Used to pick a winner when
    deduplicating multiple jobs for the same URL."""
    if job.summary_path:
        return 4
    if job.structured_transcript_path:
        return 3
    if job.raw_transcript_path:
        return 2
    if job.audio_path:
        return 1
    return 0


class JobStore:
    """SQLite-backed job store. Subscribers receive lifecycle events in-memory."""

    def __init__(self) -> None:
        self._conn = db.get_connection()
        db.init_schema(self._conn)
        # SQLite write serialization. Reads can race; writes can't.
        self._write_lock = threading.Lock()
        self._subscribers: set[asyncio.Queue[dict]] = set()

    # --- writes ----------------------------------------------------------

    def create(self, url: str, tags: Optional[list[str]] = None) -> Job:
        job = Job(id=str(uuid.uuid4()), url=url, tags=list(tags or []))
        values = tuple(_encode_for_db(c, getattr(job, c)) for c in _COLUMNS)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._write_lock:
            self._conn.execute(
                f"INSERT INTO jobs ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
        self._broadcast({"type": "job.created", "job": job.to_dict()})
        return job

    def update(self, job_id: str, **changes) -> Optional[Job]:
        if not changes:
            return self.get(job_id)
        changes["updated_at"] = time.time()
        cols = [c for c in changes if c in _COLUMNS and c != "id"]
        if not cols:
            return self.get(job_id)
        set_clause = ", ".join(f"{c} = ?" for c in cols)
        values = [_encode_for_db(c, changes[c]) for c in cols] + [job_id]
        with self._write_lock:
            cur = self._conn.execute(
                f"UPDATE jobs SET {set_clause} WHERE id = ?", values
            )
            if cur.rowcount == 0:
                return None
        job = self.get(job_id)
        if job is not None:
            self._broadcast({"type": "job.updated", "job": job.to_dict()})
        return job

    def delete(self, job_id: str) -> bool:
        with self._write_lock:
            cur = self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            if cur.rowcount == 0:
                return False
        self._broadcast({"type": "job.deleted", "job_id": job_id})
        return True

    # --- reads -----------------------------------------------------------

    def get(self, job_id: str) -> Optional[Job]:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return Job.from_row(row) if row else None

    def find_by_url(self, url: str) -> Optional[Job]:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE url = ? ORDER BY created_at ASC LIMIT 1",
            (url,),
        ).fetchone()
        return Job.from_row(row) if row else None

    def all(self, tags: Optional[list[str]] = None) -> list[Job]:
        """List all jobs, optionally filtered by tags (ANY match)."""
        if tags:
            # ANY-match across the JSON tags array
            placeholders = ", ".join("?" for _ in tags)
            rows = self._conn.execute(
                f"""
                SELECT * FROM jobs
                WHERE EXISTS (
                    SELECT 1 FROM json_each(jobs.tags)
                    WHERE json_each.value IN ({placeholders})
                )
                ORDER BY created_at ASC
                """,
                tuple(tags),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM jobs ORDER BY created_at ASC"
            ).fetchall()
        return [Job.from_row(r) for r in rows]

    def all_tags(self) -> list[str]:
        """Distinct tag values currently in use across all jobs."""
        rows = self._conn.execute(
            "SELECT DISTINCT json_each.value FROM jobs, json_each(jobs.tags) "
            "ORDER BY json_each.value ASC"
        ).fetchall()
        return [r[0] for r in rows]

    def by_status(self, statuses: Iterable[JobStatus]) -> list[Job]:
        statuses = tuple(statuses)
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        rows = self._conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders}) "
            f"ORDER BY created_at ASC",
            statuses,
        ).fetchall()
        return [Job.from_row(r) for r in rows]

    # --- startup recovery -----------------------------------------------

    def dedup_by_url(self) -> int:
        """For each URL with multiple jobs, keep the most-complete one and
        delete the rest. Tags from removed jobs are merged into the survivor.
        Returns the number of duplicates removed."""
        all_jobs = self.all()
        by_url: dict[str, list[Job]] = {}
        for j in all_jobs:
            by_url.setdefault(j.url, []).append(j)

        removed = 0
        for url, jobs in by_url.items():
            if len(jobs) <= 1:
                continue
            jobs.sort(key=lambda j: (_completeness(j), j.created_at), reverse=True)
            keeper = jobs[0]
            losers = jobs[1:]
            # Merge tags from all jobs into the keeper
            merged_tags = list(dict.fromkeys(
                t for j in jobs for t in (j.tags or [])
            ))
            if merged_tags != keeper.tags:
                self.update(keeper.id, tags=merged_tags)
            for loser in losers:
                self.delete(loser.id)
                removed += 1
                log.info("Deduped duplicate job for %s: removed %s", url, loser.id[:8])
        return removed

    def recover_interrupted(self) -> tuple[list[Job], list[Job]]:
        """Reconcile state after a process restart (JOB-1, JOB-2).

        - A job that was running goes back in the queue, up to MAX_RESTARTS
          times; its finished steps are skipped because their files exist.
        - A job interrupted more often than that is marked `failed`, so a job
          that always stops the process (for example by running out of
          memory) does not run forever.
        - Jobs that were `queued` stay queued.

        Returns (jobs failed now, jobs to queue) in creation order.
        """
        failed: list[Job] = []
        for job in self.by_status(ACTIVE_STATUSES):
            if job.restarts < MAX_RESTARTS:
                self.update(
                    job.id,
                    status="queued",
                    progress=0.0,
                    stage_label="Queued",
                    error=None,
                    restarts=job.restarts + 1,
                )
                log.warning(
                    "Queued job %s again after a restart (it was %s)",
                    job.id[:8], job.status,
                )
            else:
                error = (
                    f"{_ERROR_PREFIX[job.status]}: the service stopped during this "
                    f"step again after a restart (for example, it ran out of "
                    f"memory). To retry, submit the URL again."
                )
                failed.append(self.update(
                    job.id, status="failed", stage_label="Failed", error=error,
                ))
        requeued = self.by_status(("queued",))
        return failed, requeued

    # --- subscriber plumbing for SSE ------------------------------------

    def subscribe(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass


store = JobStore()
