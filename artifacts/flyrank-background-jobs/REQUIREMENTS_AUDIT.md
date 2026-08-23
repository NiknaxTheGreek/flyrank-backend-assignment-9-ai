# Requirements audit

| Preserved requirement | Implementation evidence |
| --- | --- |
| Independent first background-job project | `artifacts/flyrank-background-jobs/` is isolated from any human assignment implementation. |
| FastAPI + SQLite | `backend/app.py`, `backend/db.py`; SQLite database path is configurable. |
| Genuine separate worker | `backend/worker.py` is a long-running process, separate from the API process. |
| 202 before completion | `POST /api/jobs` persists only; worker claims later. |
| Input validation + idempotency | Pydantic validation and unique `jobs.idempotency_key`. |
| Persisted lifecycle states / timestamps / attempts / errors / result | `jobs` schema includes all requested fields. |
| Atomic safe claims | `BEGIN IMMEDIATE` plus guarded update in `JobStore.claim_next`. |
| Bounded retry/backoff | `max_attempts`, `next_run_at`, increasing delay, terminal `failed`. |
| Controlled transient and persistent failure | `Worker._execute`; documented deterministic modes. |
| Retry side-effect idempotency | unique `job_effects.job_id`, `INSERT OR IGNORE`. |
| Status/result semantics | `GET /api/jobs/{id}` and `/result`; 409 for non-completed state, 404 for missing. |
| Worker restart recovery | stale `running` state is returned to `retrying` on worker startup. |
| Structured logs without secret leakage | `backend/logging.py`; lifecycle context excludes input text/key. Correlated API/worker logs preserve job IDs, attempts, states, and process IDs without payload text or idempotency keys. |
| Automated tests | `tests/test_lifecycle.py`. |
| Required evidence files | README, audit, source-gap doc, verification evidence, baseline E2E output, correlated runtime trace, API/worker logs, database snapshots, and fresh check transcripts are included. |
| Human-vs-AI rematch | Explicitly pending; no human implementation was used. |