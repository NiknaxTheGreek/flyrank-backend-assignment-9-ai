from __future__ import annotations

import argparse
import os
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from .config import (
    DB_PATH,
    EXECUTION_HOLD_SECONDS,
    RETRY_DELAY_SECONDS,
    STALE_RUNNING_SECONDS,
    WORKER_POLL_SECONDS,
)
from .db import JobStore
from .logging import get_logger, log_event


class RetryableJobError(RuntimeError):
    """A failure that the worker should retry with bounded backoff."""


class NonRetryableJobError(RuntimeError):
    """A failure that should be exposed immediately as terminal."""


def analyze_text(text: str) -> dict[str, Any]:
    words = re.findall(r"\b[\w'-]+\b", text.lower())
    sentences = [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]
    keywords = [word for word, _ in Counter(words).most_common(5)]
    summary = " ".join(sentences[:2])[:280] or text[:280]
    return {
        "summary": summary,
        "wordCount": len(words),
        "sentenceCount": len(sentences),
        "topKeywords": keywords,
    }


class Worker:
    def __init__(self, db_path: str | Path = DB_PATH, worker_id: str | None = None):
        self.store = JobStore(db_path)
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.logger = get_logger("flyrank.worker")

    def recover(self) -> int:
        recovered = self.store.recover_stale_running(STALE_RUNNING_SECONDS)
        if recovered:
            log_event(self.logger, "stale_jobs_recovered", worker_id=self.worker_id, count=recovered)
        return recovered

    def run_once(self) -> bool:
        job = self.store.claim_next(self.worker_id)
        if not job:
            return False
        log_event(
            self.logger,
            "job_claimed",
            worker_id=self.worker_id,
            process_id=os.getpid(),
            job_id=job["id"],
            attempt=job["attempt_count"],
            status="running",
        )
        try:
            self._execute(job)
        except RetryableJobError as exc:
            updated = self.store.schedule_retry_or_fail(
                job["id"], str(exc), RETRY_DELAY_SECONDS * job["attempt_count"]
            )
            log_event(
                self.logger,
                "job_retry_scheduled" if updated["status"] == "retrying" else "job_failed",
                worker_id=self.worker_id,
                process_id=os.getpid(),
                job_id=job["id"],
                attempt=updated["attempt_count"],
                status=updated["status"],
                error_type=type(exc).__name__,
            )
        except NonRetryableJobError as exc:
            self.store.fail_non_retryable(job["id"], str(exc))
            log_event(
                self.logger,
                "job_failed",
                worker_id=self.worker_id,
                process_id=os.getpid(),
                job_id=job["id"],
                attempt=job["attempt_count"],
                error_type=type(exc).__name__,
            )
        except Exception as exc:  # defensive: unexpected worker errors remain retryable
            updated = self.store.schedule_retry_or_fail(
                job["id"], f"Unexpected worker failure: {type(exc).__name__}", RETRY_DELAY_SECONDS
            )
            log_event(
                self.logger,
                "job_unexpected_error",
                worker_id=self.worker_id,
                process_id=os.getpid(),
                job_id=job["id"],
                status=updated["status"],
                error_type=type(exc).__name__,
            )
        return True

    def _execute(self, job: dict[str, Any]) -> None:
        log_event(
            self.logger,
            "job_execution_started",
            worker_id=self.worker_id,
            process_id=os.getpid(),
            job_id=job["id"],
            attempt=job["attempt_count"],
            status="running",
        )
        if EXECUTION_HOLD_SECONDS:
            time.sleep(EXECUTION_HOLD_SECONDS)
        mode = job["failure_mode"]
        if mode == "transient" and job["attempt_count"] == 1:
            raise RetryableJobError("Controlled transient dependency failure")
        if mode == "permanent":
            # This intentionally models an outage that remains retryable per
            # attempt, then visibly exhausts the configured retry budget.
            raise RetryableJobError("Controlled persistent dependency failure")
        result = analyze_text(job["text_input"])
        self.store.complete_idempotently(job["id"], result)
        log_event(
            self.logger,
            "job_completed",
            worker_id=self.worker_id,
            process_id=os.getpid(),
            job_id=job["id"],
            attempt=job["attempt_count"],
        )

    def run_forever(self) -> None:
        self.store.initialize()
        self.recover()
        log_event(
            self.logger,
            "worker_started",
            worker_id=self.worker_id,
            process_id=os.getpid(),
        )
        while True:
            if not self.run_once():
                time.sleep(WORKER_POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    args = parser.parse_args()
    worker = Worker(os.getenv("JOB_DB_PATH", str(DB_PATH)))
    if args.once:
        worker.run_once()
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()