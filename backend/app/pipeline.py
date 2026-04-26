"""Single-worker async pipeline that drives jobs through their lifecycle.

Stages:
    queued -> downloading -> transcribing -> structuring -> done
                                                          \\-> failed

Why a single worker: faster-whisper holds a single GPU model; running two
transcriptions in parallel is slower than serial. Downloads could parallelize
but pipelining adds enough complexity to defer.
"""

import asyncio
import logging

from . import downloader, transcriber, structurer, summarizer
from .jobs import Job, store


log = logging.getLogger(__name__)


_queue: asyncio.Queue[str] = asyncio.Queue()
_worker_task: asyncio.Task | None = None


def submit(job: Job) -> None:
    _queue.put_nowait(job.id)


async def _run_one(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return

    loop = asyncio.get_running_loop()

    # ----- Download -------------------------------------------------------
    store.update(job_id, status="downloading", progress=0.0, stage_label="Starting download…")

    def dl_progress(pct: float, label: str) -> None:
        # Called from a thread (yt-dlp runs synchronously); marshal to loop
        loop.call_soon_threadsafe(
            lambda p=pct, l=label: store.update(
                job_id, progress=p, stage_label=l
            )
        )

    try:
        audio_path, title = await asyncio.to_thread(
            downloader.download_audio, job.url, dl_progress
        )
    except Exception as exc:
        log.exception("Download failed for %s", job.url)
        store.update(job_id, status="failed", error=f"Download failed: {exc}")
        return

    store.update(job_id, audio_path=str(audio_path), title=title)

    # ----- Transcribe -----------------------------------------------------
    store.update(job_id, status="transcribing", progress=0.0, stage_label="Loading model…")

    def tr_progress(pct: float, label: str) -> None:
        loop.call_soon_threadsafe(
            lambda p=pct, l=label: store.update(
                job_id, progress=p, stage_label=l
            )
        )

    try:
        raw_path = await asyncio.to_thread(
            transcriber.transcribe, audio_path, tr_progress
        )
    except Exception as exc:
        log.exception("Transcription failed for %s", audio_path)
        store.update(job_id, status="failed", error=f"Transcription failed: {exc}")
        return

    store.update(job_id, raw_transcript_path=str(raw_path))

    # ----- Structure ------------------------------------------------------
    store.update(
        job_id,
        status="structuring",
        progress=0.0,
        stage_label="Asking Claude to structure transcript…",
    )

    def st_progress(pct: float, label: str) -> None:
        # structure_transcript runs on the loop, but the callback may also be
        # invoked from inside an awaited subprocess; route through threadsafe
        # for safety/consistency with the other stages.
        loop.call_soon_threadsafe(
            lambda p=pct, l=label: store.update(
                job_id, progress=p, stage_label=l
            )
        )

    try:
        structured_path = await structurer.structure_transcript(
            raw_path, on_progress=st_progress
        )
    except Exception as exc:
        log.exception("Structuring failed for %s", raw_path)
        store.update(job_id, status="failed", error=f"Structuring failed: {exc}")
        return

    store.update(
        job_id,
        structured_transcript_path=str(structured_path),
    )

    # ----- Summarize ------------------------------------------------------
    store.update(
        job_id,
        status="summarizing",
        progress=0.0,
        stage_label="Asking Opus to summarize…",
    )

    try:
        summary_path = await summarizer.summarize_transcript(structured_path)
    except Exception as exc:
        log.exception("Summarization failed for %s", structured_path)
        store.update(job_id, status="failed", error=f"Summarization failed: {exc}")
        return

    store.update(
        job_id,
        status="done",
        progress=100.0,
        stage_label="Done",
        summary_path=str(summary_path),
    )


async def _worker_loop() -> None:
    log.info("Pipeline worker started")
    while True:
        job_id = await _queue.get()
        try:
            await _run_one(job_id)
        except Exception:
            log.exception("Unexpected error processing job %s", job_id)
        finally:
            _queue.task_done()


def start_worker() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())


async def stop_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
