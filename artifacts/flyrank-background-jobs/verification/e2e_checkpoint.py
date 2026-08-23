"""Live API + separate-worker checkpoint recorder for the assignment."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "verification"
OBSERVATIONS_PATH = OUTPUT / "e2e-observations.json"
RESTART_JOB_PATH = OUTPUT / "restart-job-id.txt"
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:80/api").rstrip("/")


def request(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    payload = json.dumps(body).encode() if body is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request_obj = Request(f"{BASE_URL}{path}", data=payload, headers=request_headers, method=method)
    try:
        with urlopen(request_obj, timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def post_job(text: str, mode: str, key: str) -> tuple[int, dict]:
    return request(
        "POST",
        "/jobs",
        {"text": text, "failureMode": mode},
        {"Idempotency-Key": key},
    )


def job_state(job_id: str) -> dict:
    code, payload = request("GET", f"/jobs/{job_id}")
    assert code == 200, payload
    return payload


def wait_for(job_id: str, expected: set[str], timeout: float = 8) -> dict:
    deadline = time.monotonic() + timeout
    last = job_state(job_id)
    while time.monotonic() < deadline:
        if last["status"] in expected:
            return last
        time.sleep(0.05)
        last = job_state(job_id)
    raise RuntimeError(f"Job {job_id} did not reach {expected}; last state: {last}")


def database_snapshot() -> list[dict]:
    db_path = Path(os.getenv("JOB_DB_PATH", ROOT / "data" / "jobs.sqlite3"))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, status, failure_mode, attempt_count, max_attempts,
                   execution_count, created_at, started_at, completed_at,
                   last_error, idempotency_key
            FROM jobs
            ORDER BY created_at
            """
        ).fetchall()
        return [dict(row) for row in rows]


def run_checkpoint() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = uuid.uuid4().hex[:8]
    observations: dict[str, object] = {
        "baseUrl": BASE_URL,
        "checkpoint": "live separate API and worker processes",
        "observedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    normal_code, normal_accept = post_job(
        "A durable queue keeps requests responsive while workers deliver reliable results.",
        "none",
        f"e2e-normal-{stamp}",
    )
    normal_pending = job_state(normal_accept["jobId"])
    normal_completed = wait_for(normal_accept["jobId"], {"completed"})
    normal_result_code, normal_result = request("GET", f"/jobs/{normal_accept['jobId']}/result")
    observations["normal"] = {
        "acceptHttpStatus": normal_code,
        "accepted": normal_accept,
        "immediateState": normal_pending,
        "completedState": normal_completed,
        "resultHttpStatus": normal_result_code,
        "result": normal_result,
    }

    idempotency_key = f"e2e-idempotent-{stamp}"
    first_code, first = post_job("One key must be one execution.", "none", idempotency_key)
    second_code, second = post_job("One key must be one execution.", "none", idempotency_key)
    idempotent_done = wait_for(first["jobId"], {"completed"})
    list_code, all_jobs = request("GET", "/jobs")
    matches = [job for job in all_jobs if job["id"] == first["jobId"]]
    observations["idempotency"] = {
        "firstHttpStatus": first_code,
        "secondHttpStatus": second_code,
        "first": first,
        "second": second,
        "sameJobId": first["jobId"] == second["jobId"],
        "persistedMatchingJobCount": len(matches),
        "completedState": idempotent_done,
        "listHttpStatus": list_code,
    }

    transient_code, transient = post_job("Retry this exactly once.", "transient", f"e2e-transient-{stamp}")
    transient_retrying = wait_for(transient["jobId"], {"retrying"})
    transient_done = wait_for(transient["jobId"], {"completed"})
    observations["transientFailure"] = {
        "acceptHttpStatus": transient_code,
        "accepted": transient,
        "retryingState": transient_retrying,
        "completedState": transient_done,
    }

    permanent_code, permanent = post_job("Exhaust the bounded retry budget.", "permanent", f"e2e-permanent-{stamp}")
    permanent_failed = wait_for(permanent["jobId"], {"failed"}, timeout=10)
    permanent_result_code, permanent_result = request("GET", f"/jobs/{permanent['jobId']}/result")
    observations["persistentFailure"] = {
        "acceptHttpStatus": permanent_code,
        "accepted": permanent,
        "failedState": permanent_failed,
        "resultHttpStatus": permanent_result_code,
        "resultNotAvailableResponse": permanent_result,
    }

    OBSERVATIONS_PATH.write_text(json.dumps(observations, indent=2, sort_keys=True) + "\n")
    RESTART_JOB_PATH.write_text(normal_accept["jobId"] + "\n")
    (OUTPUT / "database-snapshot.json").write_text(
        json.dumps(database_snapshot(), indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(observations, indent=2))


def verify_after_restart(job_id: str) -> None:
    observations = json.loads(OBSERVATIONS_PATH.read_text())
    status_code, status_payload = request("GET", f"/jobs/{job_id}")
    result_code, result_payload = request("GET", f"/jobs/{job_id}/result")
    observations["afterRestart"] = {
        "jobId": job_id,
        "statusHttpStatus": status_code,
        "status": status_payload,
        "resultHttpStatus": result_code,
        "result": result_payload,
        "persistenceVerified": status_code == 200
        and status_payload.get("status") == "completed"
        and result_code == 200,
    }
    OBSERVATIONS_PATH.write_text(json.dumps(observations, indent=2, sort_keys=True) + "\n")
    print(json.dumps(observations["afterRestart"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-restart", metavar="JOB_ID")
    args = parser.parse_args()
    if args.verify_restart:
        verify_after_restart(args.verify_restart)
    else:
        run_checkpoint()