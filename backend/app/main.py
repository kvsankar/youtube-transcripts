"""FastAPI app: REST + SSE for the YouTube transcript pipeline."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, HttpUrl

from . import pipeline
from .jobs import store


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    pipeline.start_worker()
    removed = store.dedup_by_url()
    if removed:
        log.warning("Removed %d duplicate job row(s) on startup", removed)
    failed, requeued = store.recover_interrupted()
    if failed:
        log.warning("Marked %d in-flight job(s) as failed after restart", len(failed))
    for job in requeued:
        pipeline.submit(job)
    yield
    await pipeline.stop_worker()


app = FastAPI(title="YouTube Transcripts", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateJobsRequest(BaseModel):
    urls: list[HttpUrl]
    tags: Optional[list[str]] = None


class TagsRequest(BaseModel):
    tags: list[str]


@app.post("/api/jobs")
def create_jobs(payload: CreateJobsRequest) -> dict:
    """Submit URLs. If a URL has already been submitted, the existing job is
    returned (no duplicate row). If that existing job is in `failed` state,
    it is reset and re-queued."""
    incoming_tags = payload.tags or []
    results = []
    for url in payload.urls:
        url_str = str(url)
        existing = store.find_by_url(url_str)
        if existing is None:
            job = store.create(url_str, tags=incoming_tags)
            pipeline.submit(job)
            results.append(job.to_dict())
            continue

        # Merge any new tags into the existing job
        if incoming_tags:
            merged = list(dict.fromkeys([*existing.tags, *incoming_tags]))
            if merged != existing.tags:
                store.update(existing.id, tags=merged)

        if existing.status == "failed":
            store.update(
                existing.id,
                status="queued",
                error=None,
                progress=0.0,
                stage_label="Queued",
            )
            revived = store.get(existing.id)
            if revived is not None:
                pipeline.submit(revived)
                results.append(revived.to_dict())
                continue

        # Already in-flight or done — return as-is, no action
        latest = store.get(existing.id)
        if latest is not None:
            results.append(latest.to_dict())

    return {"jobs": results}


@app.get("/api/jobs")
def list_jobs(
    tag: Optional[list[str]] = Query(default=None),
) -> dict:
    """List jobs, optionally filtered by one or more tags (ANY match)."""
    return {"jobs": [j.to_dict() for j in store.all(tags=tag)]}


@app.get("/api/tags")
def list_tags() -> dict:
    return {"tags": store.all_tags()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.patch("/api/jobs/{job_id}/tags")
def set_job_tags(job_id: str, payload: TagsRequest) -> dict:
    # Deduplicate while preserving order, drop empty/whitespace tags
    cleaned = list(dict.fromkeys(t.strip() for t in payload.tags if t.strip()))
    job = store.update(job_id, tags=cleaned)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    if not store.delete(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"deleted": job_id}


@app.get("/api/jobs/{job_id}/raw", response_class=PlainTextResponse)
def get_raw(job_id: str) -> str:
    job = store.get(job_id)
    if job is None or not job.raw_transcript_path:
        raise HTTPException(status_code=404, detail="raw transcript not available")
    with open(job.raw_transcript_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/jobs/{job_id}/structured", response_class=PlainTextResponse)
def get_structured(job_id: str) -> str:
    job = store.get(job_id)
    if job is None or not job.structured_transcript_path:
        raise HTTPException(status_code=404, detail="structured transcript not available")
    with open(job.structured_transcript_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/jobs/{job_id}/summary", response_class=PlainTextResponse)
def get_summary(job_id: str) -> str:
    job = store.get(job_id)
    if job is None or not job.summary_path:
        raise HTTPException(status_code=404, detail="summary not available")
    with open(job.summary_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/events")
async def events():
    """SSE stream of all job lifecycle events."""

    async def event_source():
        queue = store.subscribe()
        try:
            snapshot = {"type": "snapshot", "jobs": [j.to_dict() for j in store.all()]}
            yield _format_sse(snapshot)

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            store.unsubscribe(queue)

    return StreamingResponse(event_source(), media_type="text/event-stream")


def _format_sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
