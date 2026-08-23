from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.db import JobStore
from backend.worker import Worker


def setup(tmp_path: Path) -> tuple[TestClient, JobStore, Worker]:
    database = tmp_path / "jobs.sqlite3"
    store = JobStore(database)
    store.initialize()
    return TestClient(create_app(database)), store, Worker(database, worker_id="test-worker")


def accept(client: TestClient, text: str = "A durable job is useful.", mode: str = "none", key: str | None = None):
    return client.post(
        "/api/jobs",
        headers={"Idempotency-Key": key or str(uuid.uuid4())},
        json={"text": text, "failureMode": mode},
    )


def test_acceptance_is_202_and_response_precedes_worker(tmp_path: Path) -> None:
    client, _, _ = setup(tmp_path)
    response = accept(client)
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['jobId']}").json()
    assert job["status"] == "pending"
    assert job["attemptCount"] == 0


def test_idempotency_key_deduplicates_to_one_persisted_job(tmp_path: Path) -> None:
    client, store, _ = setup(tmp_path)
    key = "same-request"
    first, second = accept(client, key=key), accept(client, key=key)
    assert first.json()["jobId"] == second.json()["jobId"]
    assert second.json()["deduplicated"] is True
    assert len(store.list_recent()) == 1


def test_normal_transition_and_result(tmp_path: Path) -> None:
    client, _, worker = setup(tmp_path)
    accepted = accept(client, "Reliable workers make asynchronous systems observable.").json()
    assert worker.run_once() is True
    job = client.get(f"/api/jobs/{accepted['jobId']}").json()
    assert job["status"] == "completed"
    result = client.get(f"/api/jobs/{accepted['jobId']}/result")
    assert result.status_code == 200
    assert result.json()["result"]["wordCount"] > 0


def test_transient_failure_retries_then_completes(tmp_path: Path) -> None:
    client, _, worker = setup(tmp_path)
    job_id = accept(client, mode="transient").json()["jobId"]
    worker.run_once()
    retrying = client.get(f"/api/jobs/{job_id}").json()
    assert retrying["status"] == "retrying"
    assert retrying["attemptCount"] == 1
    time.sleep(0.45)
    worker.run_once()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"


def test_permanent_mode_exhausts_bounded_retries(tmp_path: Path) -> None:
    client, _, worker = setup(tmp_path)
    job_id = accept(client, mode="permanent").json()["jobId"]
    for _ in range(3):
        worker.run_once()
        time.sleep(0.8)
    failed = client.get(f"/api/jobs/{job_id}").json()
    assert failed["status"] == "failed"
    assert failed["attemptCount"] == failed["maxAttempts"]
    assert "Controlled persistent" in failed["lastError"]


def test_retries_do_not_duplicate_effects_or_results(tmp_path: Path) -> None:
    client, store, worker = setup(tmp_path)
    job_id = accept(client, mode="transient").json()["jobId"]
    worker.run_once()
    time.sleep(0.45)
    worker.run_once()
    assert store.effect_count(job_id) == 1
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 200


def test_invalid_input_is_400(tmp_path: Path) -> None:
    client, _, _ = setup(tmp_path)
    response = client.post("/api/jobs", headers={"Idempotency-Key": "invalid"}, json={"text": "   "})
    assert response.status_code == 400


def test_missing_job_and_result_not_ready_are_predictable(tmp_path: Path) -> None:
    client, _, _ = setup(tmp_path)
    assert client.get("/api/jobs/missing").status_code == 404
    job_id = accept(client).json()["jobId"]
    unavailable = client.get(f"/api/jobs/{job_id}/result")
    assert unavailable.status_code == 409


def test_persistence_survives_api_and_worker_recreation(tmp_path: Path) -> None:
    client, _, worker = setup(tmp_path)
    job_id = accept(client).json()["jobId"]
    worker.run_once()
    reloaded_client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    assert reloaded_client.get(f"/api/jobs/{job_id}/result").status_code == 200


def test_worker_recovers_stale_running_work(tmp_path: Path) -> None:
    client, store, worker = setup(tmp_path)
    job_id = accept(client).json()["jobId"]
    claimed = store.claim_next("crashed-worker")
    assert claimed and claimed["status"] == "running"
    assert store.recover_stale_running(0) == 1
    recovered = client.get(f"/api/jobs/{job_id}").json()
    assert recovered["status"] == "retrying"
    worker.run_once()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"