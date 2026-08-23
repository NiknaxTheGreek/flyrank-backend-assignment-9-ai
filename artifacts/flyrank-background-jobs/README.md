# FlyRank Backend Assignment 9 — First Background Job

A deliberately small FastAPI + SQLite job system demonstrating the lifecycle:

`request → accepted (202) → persisted pending job → separately running worker → status/result`

The business operation is a simple deterministic text analysis. The focus is the job system: durable state, safe claiming, retries, idempotency, observability, and recovery.

## Run

Start the API and worker in **separate terminals/processes**:

```bash
python -m uvicorn backend.app:app --app-dir artifacts/flyrank-background-jobs --host 0.0.0.0 --port 8000
python -m backend.worker
```

The web interface calls the API at `/api`. For local standalone work, set `JOB_DB_PATH` consistently for both processes.

## API

| Endpoint | Behavior |
| --- | --- |
| `POST /api/jobs` | Requires `Idempotency-Key`; validates input and returns `202` with a job identifier. |
| `GET /api/jobs` | Lists recent persisted jobs. |
| `GET /api/jobs/summary` | State counts for the job system. |
| `GET /api/jobs/{jobId}` | Returns status, attempts, timestamps, and safe observability fields. |
| `GET /api/jobs/{jobId}/result` | Returns `200` only when completed; `409` while active or failed; `404` when missing. |

Request body:

```json
{"text":"Useful text to analyze.","failureMode":"none"}
```

`failureMode` can be:

- `none` — completes normally.
- `transient` — fails once with a controlled retryable error, then succeeds.
- `permanent` — simulates a retryable dependency outage on every attempt and visibly becomes `failed` after the bounded retry budget. It is named for the persistent outage, not because the error is non-retryable.

## Design notes

- **Durability:** Jobs and results live in SQLite; API and worker recreate their repositories from the same file.
- **Safe claiming:** `BEGIN IMMEDIATE` protects the queued-to-running claim, so two workers cannot claim the same due job.
- **Idempotency:** A unique `idempotency_key` returns the original job for repeated submissions. A unique `job_effects.job_id` prevents repeated completion side effects if a worker retries after a crash.
- **Retries:** Only `RetryableJobError` schedules a retry, with a bounded max attempt count and increasing delay. Non-retryable errors become terminal immediately.
- **Crash recovery:** Worker startup returns stale `running` jobs to `retrying`. Assumption: a job whose lease (`claimed_at`) is older than `JOB_STALE_RUNNING_SECONDS` belongs to an unavailable worker. This is a pragmatic single-node SQLite lease, not distributed coordination.
- **Logs:** API and worker emit structured JSON containing lifecycle fields (event, job id, attempt, status, error type) but omit job text and idempotency values.
- **Evidence-only running window:** `JOB_EXECUTION_HOLD_SECONDS` defaults to `0`. The correlated verification harness may set a short value in its isolated processes so the real `running` state can be observed; it is not required for normal operation.

## Tests

```bash
PYTHONPATH=artifacts/flyrank-background-jobs pytest artifacts/flyrank-background-jobs/tests -q
```

The tests cover acceptance, prompt response, validation, idempotency, result rules, normal completion, retry success, terminal exhaustion, side-effect idempotency, persistence, and recovery scaffolding.

See `REQUIREMENTS_AUDIT.md`, `VERIFICATION_EVIDENCE.md`, and `SOURCE_GAP_AND_ASSUMPTIONS.md` for scope, evidence, and source limits. The strongest reproducible runtime proof is `verification/correlated_runtime_trace.py`.