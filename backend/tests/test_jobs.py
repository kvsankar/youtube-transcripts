"""Tests for JOB-1 and JOB-2 in docs/specs.md (restart recovery)."""

import pytest

from app import db, jobs


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    return jobs.JobStore()


def _restart(_store):
    # A new store on the same database file stands for the restarted process.
    return jobs.JobStore()


def test_job1_running_job_is_requeued(store):
    running = store.create("https://example.com/a")
    store.update(running.id, status="transcribing", progress=40.0)
    waiting = store.create("https://example.com/b")

    failed, requeued = _restart(store).recover_interrupted()

    assert failed == []
    assert [j.id for j in requeued] == [running.id, waiting.id]
    again = store.get(running.id)
    assert again.status == "queued"
    assert again.error is None
    assert again.restarts == 1


def test_job2_second_interruption_fails_with_step_name(store):
    job = store.create("https://example.com/a")
    store.update(job.id, status="transcribing")
    _restart(store).recover_interrupted()
    store.update(job.id, status="transcribing")

    failed, requeued = _restart(store).recover_interrupted()

    assert [j.id for j in failed] == [job.id]
    assert requeued == []
    got = store.get(job.id)
    assert got.status == "failed"
    assert got.error.startswith("Transcription failed: ")
    assert "submit the URL again" in got.error


def test_job2_old_failures_are_not_counted(store):
    old = store.create("https://example.com/a")
    store.update(old.id, status="failed", error="Download failed: 403")

    failed, requeued = _restart(store).recover_interrupted()

    assert failed == [] and requeued == []
    assert store.get(old.id).error == "Download failed: 403"


def test_job2_resubmitting_resets_the_allowance(store, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main, pipeline

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(pipeline, "submit", lambda job: None)
    job = store.create("https://example.com/a")
    store.update(job.id, status="failed", error="Transcription failed: x", restarts=1)

    # No `with`: the lifespan (worker start, recovery) is not under test here.
    r = TestClient(main.app).post("/api/jobs", json={"urls": ["https://example.com/a"]})

    assert r.status_code == 200
    got = store.get(job.id)
    assert got.status == "queued"
    assert got.restarts == 0
