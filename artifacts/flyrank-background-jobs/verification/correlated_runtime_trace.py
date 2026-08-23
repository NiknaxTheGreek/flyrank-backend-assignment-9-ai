"""Create a correlated, isolated FastAPI + worker runtime evidence bundle.

This is intentionally an integration harness rather than a unit test. It
starts a real API process and a real worker process against a fresh SQLite
database, records their process IDs and JSON logs, then preserves observed
status responses and a safe query snapshot under verification/.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import IO, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "verification"
DB_PATH = OUTPUT / "correlated-runtime.sqlite3"
API_LOG_PATH = OUTPUT / "correlated-api.log"
WORKER_LOG_PATH = OUTPUT / "correlated-worker.log"
OBSERVATIONS_PATH = OUTPUT / "correlated-runtime-observations.json"
SNAPSHOT_PATH = OUTPUT / "correlated-runtime-database-snapshot.json"
TYPECHECK_MARKER = OUTPUT / "correlated-runtime-trace-command.txt"
PORT = 8011
BASE_URL = f"http://127.0.0.1:{PORT}/api"


def request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(body).encode() if body is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    req = Request(f"{BASE_URL}{path}", data=payload, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def wait_for_api() -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            code, _ = request("GET", "/healthz")
            if code == 200:
                return
        except (URLError, ConnectionError):
            time.sleep(0.05)
    raise RuntimeError("Isolated FastAPI process did not become healthy")


def get_status(job_id: str) -> dict[str, Any]:
    code, payload = request("GET", f"/jobs/{job_id}")
    if code != 200:
        raise RuntimeError(f"Unexpected job status response: {code} {payload}")
    return payload


def wait_for_status(
    job_id: str,
    expected: set[str],
    observed: list[dict[str, Any]],
    timeout: float = 10,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = get_status(job_id)
        observed.append(
            {
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": status["status"],
                "attemptCount": status["attemptCount"],
                "lastError": status["lastError"],
            }
        )
        if status["status"] in expected:
            return status
        time.sleep(0.05)
    raise RuntimeError(f"Job {job_id} did not reach {sorted(expected)}")


def post_job(mode: str, key: str) -> tuple[int, dict[str, Any]]:
    return request(
        "POST",
        "/jobs",
        {"text": f"Correlated evidence job for {mode} mode.", "failureMode": mode},
        {"Idempotency-Key": key},
    )


def start_process(
    command: list[str],
    env: dict[str, str],
    log_path: Path,
    log_mode: str,
) -> tuple[subprocess.Popen[bytes], IO[bytes]]:
    log_handle = log_path.open(log_mode)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    return process, log_handle


def stop_process(process: subprocess.Popen[bytes] | None, log_handle: IO[bytes] | None) -> None:
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if log_handle:
        log_handle.close()


def database_snapshot() -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, status, failure_mode, attempt_count, max_attempts,
                   execution_count, created_at, started_at, completed_at, last_error
            FROM jobs
            ORDER BY created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def remove_trace_database() -> None:
    for path in (DB_PATH, Path(f"{DB_PATH}-shm"), Path(f"{DB_PATH}-wal")):
        path.unlink(missing_ok=True)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    remove_trace_database()
    for path in (API_LOG_PATH, WORKER_LOG_PATH, OBSERVATIONS_PATH, SNAPSHOT_PATH):
        path.unlink(missing_ok=True)

    trace_id = f"trace-{uuid.uuid4().hex[:10]}"
    base_env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "JOB_DB_PATH": str(DB_PATH),
        "JOB_MAX_ATTEMPTS": "3",
        "JOB_RETRY_DELAY_SECONDS": "0.25",
        "WORKER_POLL_SECONDS": "0.03",
        # Evidence-only: makes the real `running` state observable. Default
        # application behavior remains 0 seconds.
        "JOB_EXECUTION_HOLD_SECONDS": "0.45",
    }
    api_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--no-access-log",
    ]
    worker_command = [sys.executable, "-m", "backend.worker"]
    TYPECHECK_MARKER.write_text(
        f"trace_id={trace_id}\napi_command={' '.join(api_command)}\nworker_command={' '.join(worker_command)}\n"
    )

    api: subprocess.Popen[bytes] | None = None
    worker: subprocess.Popen[bytes] | None = None
    api_log: IO[bytes] | None = None
    worker_log: IO[bytes] | None = None
    observations: dict[str, Any] = {
        "traceId": trace_id,
        "purpose": "Correlated separate-process lifecycle evidence",
        "baseUrl": BASE_URL,
        "executionHoldSeconds": 0.45,
        "processes": {},
    }

    try:
        api, api_log = start_process(api_command, base_env, API_LOG_PATH, "wb")
        wait_for_api()
        observations["processes"]["apiInitial"] = {"pid": api.pid, "command": api_command}

        transient_code, transient_accept = post_job("transient", f"{trace_id}-transient")
        transient_id = transient_accept["jobId"]
        transient_pending = get_status(transient_id)

        worker, worker_log = start_process(worker_command, base_env, WORKER_LOG_PATH, "wb")
        observations["processes"]["workerInitial"] = {"pid": worker.pid, "command": worker_command}
        transient_states: list[dict[str, Any]] = []
        transient_running_one = wait_for_status(transient_id, {"running"}, transient_states)
        transient_retrying = wait_for_status(transient_id, {"retrying"}, transient_states)
        transient_running_two = wait_for_status(transient_id, {"running"}, transient_states)
        transient_completed = wait_for_status(transient_id, {"completed"}, transient_states)
        transient_result_code, transient_result = request("GET", f"/jobs/{transient_id}/result")
        observations["transientLifecycle"] = {
            "jobId": transient_id,
            "acceptHttpStatus": transient_code,
            "accepted": transient_accept,
            "pending": transient_pending,
            "runningAttemptOne": transient_running_one,
            "retrying": transient_retrying,
            "runningAttemptTwo": transient_running_two,
            "completed": transient_completed,
            "resultHttpStatus": transient_result_code,
            "result": transient_result,
            "observedStatuses": transient_states,
        }

        permanent_code, permanent_accept = post_job("permanent", f"{trace_id}-permanent")
        permanent_id = permanent_accept["jobId"]
        permanent_states: list[dict[str, Any]] = []
        permanent_running = wait_for_status(permanent_id, {"running"}, permanent_states)
        permanent_retrying = wait_for_status(permanent_id, {"retrying"}, permanent_states)
        permanent_failed = wait_for_status(permanent_id, {"failed"}, permanent_states, timeout=12)
        permanent_result_code, permanent_result = request("GET", f"/jobs/{permanent_id}/result")
        observations["permanentLifecycle"] = {
            "jobId": permanent_id,
            "acceptHttpStatus": permanent_code,
            "accepted": permanent_accept,
            "running": permanent_running,
            "retrying": permanent_retrying,
            "failed": permanent_failed,
            "resultHttpStatus": permanent_result_code,
            "result": permanent_result,
            "observedStatuses": permanent_states,
        }

        stop_process(worker, worker_log)
        worker, worker_log = None, None
        stop_process(api, api_log)
        api, api_log = None, None

        api, api_log = start_process(api_command, base_env, API_LOG_PATH, "ab")
        wait_for_api()
        worker, worker_log = start_process(worker_command, base_env, WORKER_LOG_PATH, "ab")
        observations["processes"]["apiRestarted"] = {"pid": api.pid, "command": api_command}
        observations["processes"]["workerRestarted"] = {"pid": worker.pid, "command": worker_command}
        restart_status_code, restart_status = request("GET", f"/jobs/{transient_id}")
        restart_result_code, restart_result = request("GET", f"/jobs/{transient_id}/result")
        observations["restartPersistence"] = {
            "jobId": transient_id,
            "statusHttpStatus": restart_status_code,
            "status": restart_status,
            "resultHttpStatus": restart_result_code,
            "result": restart_result,
            "persistenceVerified": restart_status_code == 200
            and restart_status.get("status") == "completed"
            and restart_result_code == 200,
        }

        OBSERVATIONS_PATH.write_text(json.dumps(observations, indent=2, sort_keys=True) + "\n")
        SNAPSHOT_PATH.write_text(json.dumps(database_snapshot(), indent=2, sort_keys=True) + "\n")
        print(json.dumps(observations, indent=2, sort_keys=True))
    finally:
        stop_process(worker, worker_log)
        stop_process(api, api_log)
        remove_trace_database()


if __name__ == "__main__":
    main()