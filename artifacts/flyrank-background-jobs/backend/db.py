from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import MAX_ATTEMPTS

TERMINAL_STATES = {"completed", "failed"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


class JobStore:
    """Small SQLite repository. Each operation opens its own connection.

    SQLite BEGIN IMMEDIATE provides the claim lock. That makes the transition
    from queued -> running atomic across independent API and worker processes.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.db_path,
            timeout=10,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    text_input TEXT NOT NULL,
                    failure_mode TEXT NOT NULL CHECK (failure_mode IN ('none', 'transient', 'permanent')),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'retrying', 'completed', 'failed')),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    next_run_at TEXT,
                    last_error TEXT,
                    result_json TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    claimed_by TEXT,
                    claimed_at TEXT,
                    execution_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS jobs_ready_index
                    ON jobs(status, next_run_at, created_at);
                CREATE TABLE IF NOT EXISTS job_effects (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_or_get(
        self, *, text: str, failure_mode: str, idempotency_key: str
    ) -> tuple[dict[str, Any], bool]:
        self.initialize()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                conn.commit()
                return self._public(existing), True

            job_id = str(uuid.uuid4())
            now = iso_now()
            conn.execute(
                """
                INSERT INTO jobs (
                    id, text_input, failure_mode, status, attempt_count, max_attempts,
                    created_at, next_run_at, idempotency_key
                ) VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                """,
                (job_id, text, failure_mode, MAX_ATTEMPTS, now, now, idempotency_key),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            conn.commit()
            return self._public(row), False

    def get(self, job_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._public(row) if row else None

    def get_internal(self, job_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._public(row) for row in rows]

    def summary(self) -> dict[str, int]:
        self.initialize()
        result = {state: 0 for state in ("pending", "running", "retrying", "completed", "failed")}
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
        for row in rows:
            result[row["status"]] = row["count"]
        result["total"] = sum(result.values())
        return {"total": result["total"], **{state: result[state] for state in result if state != "total"}}

    def claim_next(self, worker_id: str) -> dict[str, Any] | None:
        """Claim exactly one due job while holding SQLite's writer lock."""
        self.initialize()
        now = iso_now()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status IN ('pending', 'retrying') AND next_run_at <= ?
                ORDER BY next_run_at, created_at
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    execution_count = execution_count + 1,
                    started_at = COALESCE(started_at, ?),
                    claimed_at = ?,
                    claimed_by = ?
                WHERE id = ? AND status IN ('pending', 'retrying')
                """,
                (now, now, worker_id, row["id"]),
            )
            claimed = conn.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
            conn.commit()
        return dict(claimed)

    def schedule_retry_or_fail(self, job_id: str, error: str, delay_seconds: float) -> dict[str, Any]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                conn.rollback()
                raise KeyError(job_id)
            if job["attempt_count"] >= job["max_attempts"]:
                conn.execute(
                    """
                    UPDATE jobs SET status = 'failed', last_error = ?, completed_at = ?,
                    next_run_at = NULL, claimed_at = NULL, claimed_by = NULL
                    WHERE id = ?
                    """,
                    (error, iso_now(), job_id),
                )
            else:
                next_run = (utc_now() + timedelta(seconds=delay_seconds)).isoformat()
                conn.execute(
                    """
                    UPDATE jobs SET status = 'retrying', last_error = ?, next_run_at = ?,
                    claimed_at = NULL, claimed_by = NULL
                    WHERE id = ?
                    """,
                    (error, next_run, job_id),
                )
            updated = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            conn.commit()
        return dict(updated)

    def fail_non_retryable(self, job_id: str, error: str) -> dict[str, Any]:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET status = 'failed', last_error = ?, completed_at = ?,
                next_run_at = NULL, claimed_at = NULL, claimed_by = NULL
                WHERE id = ?
                """,
                (error, iso_now(), job_id),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row)

    def complete_idempotently(self, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
        """Record the business side effect once, then make the job terminal.

        The unique job_effects.job_id constraint is the idempotency guard if a
        worker crashes after writing the effect but before finalizing the job.
        """
        payload = json.dumps(result, sort_keys=True)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO job_effects(job_id, result_json, created_at) VALUES (?, ?, ?)",
                (job_id, payload, iso_now()),
            )
            effect = conn.execute(
                "SELECT result_json FROM job_effects WHERE job_id = ?", (job_id,)
            ).fetchone()
            conn.execute(
                """
                UPDATE jobs
                SET status = 'completed', result_json = ?, completed_at = ?,
                    next_run_at = NULL, last_error = NULL, claimed_at = NULL, claimed_by = NULL
                WHERE id = ? AND status <> 'completed'
                """,
                (effect["result_json"], iso_now(), job_id),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            conn.commit()
        return dict(row)

    def recover_stale_running(self, stale_seconds: float) -> int:
        cutoff = (utc_now() - timedelta(seconds=stale_seconds)).isoformat()
        with self.connection() as conn:
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = 'retrying',
                    last_error = 'Recovered stale running job after worker restart',
                    next_run_at = ?,
                    claimed_at = NULL,
                    claimed_by = NULL
                WHERE status = 'running' AND claimed_at <= ?
                """,
                (iso_now(), cutoff),
            )
        return updated.rowcount

    def effect_count(self, job_id: str) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM job_effects WHERE job_id = ?", (job_id,)
            ).fetchone()
        return int(row["count"])

    def _public(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise ValueError("Expected a job row")
        return {
            "id": row["id"],
            "status": row["status"],
            "textPreview": row["text_input"][:120],
            "failureMode": row["failure_mode"],
            "attemptCount": row["attempt_count"],
            "maxAttempts": row["max_attempts"],
            "createdAt": row["created_at"],
            "startedAt": row["started_at"],
            "completedAt": row["completed_at"],
            "nextRunAt": row["next_run_at"],
            "lastError": row["last_error"],
            "idempotencyKey": row["idempotency_key"],
        }