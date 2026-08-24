# FlyRank Backend Assignment 9 — First Background Job

A deliberately small FastAPI + SQLite background-job system demonstrating the recovered S3 lifecycle:

```text
request → 202 Accepted → persisted pending job → separate worker → status/result
```

The selected slow-operation stand-in is deterministic text analysis so the assignment can focus on asynchronous execution, retries, idempotency, observability and restart behavior without depending on an external provider.

## API

| Endpoint | Behavior |
| --- | --- |
| `POST /api/jobs` | Requires `Idempotency-Key`; validates input and returns HTTP `202` with a job identifier. |
| `GET /api/jobs` | Lists recent persisted jobs. |
| `GET /api/jobs/summary` | Returns state counts for the job system. |
| `GET /api/jobs/{jobId}` | Returns persisted status, attempts, timestamps and failure fields. |
| `GET /api/jobs/{jobId}/result` | Returns `200` only when completed; controlled non-success response otherwise. |

Request body:

```json
{"text":"Useful text to analyze.","failureMode":"none"}
```

`failureMode` is a deterministic verification switch:

- `none` — completes normally;
- `transient` — fails once, is retried, then succeeds;
- `permanent` — simulates a repeatedly retryable dependency outage until the bounded attempt budget is exhausted and the job becomes `failed`.

The exact route names, SQLite, status vocabulary, retry count and business operation are local choices because recovered S3 does not prescribe them.

## Run

Install from the repository root:

```bash
python -m pip install .
```

Then start the API and worker in **separate terminals/processes**:

```bash
python -m uvicorn backend.app:app \
  --app-dir artifacts/flyrank-background-jobs \
  --host 127.0.0.1 \
  --port 8000

python -m backend.worker
```

If `JOB_DB_PATH` is overridden, both processes must point to the same database file.

## Reliability design

- **Durability:** jobs and results live in SQLite rather than process memory.
- **Safe claiming:** `BEGIN IMMEDIATE` plus a guarded update prevents two local workers from claiming the same due job simultaneously.
- **Submission idempotency:** `jobs.idempotency_key` is unique; repeated submissions with the same key return the original job.
- **Side-effect idempotency:** `job_effects.job_id` is unique and completion uses an idempotent insert, protecting the completion effect if execution is repeated.
- **Retries:** retryable failures move to `retrying` with a bounded attempt count and increasing delay.
- **Failure visibility:** terminal failures retain persisted status, attempts and `lastError`; structured API/worker logs include lifecycle metadata without logging submitted text or idempotency values.
- **Crash/restart recovery:** stale `running` work is returned to retryable state on worker startup using a simple single-node lease assumption.

## Tests and runtime verification

```bash
PYTHONPATH=artifacts/flyrank-background-jobs \
python -m pytest artifacts/flyrank-background-jobs/tests -q

python artifacts/flyrank-background-jobs/verification/correlated_runtime_trace.py
```

GitHub Actions run `32712518867` passed the current repaired branch with:

- clean `pip install .`;
- **10 lifecycle tests passed**;
- a real API + separate worker trace proving `202`, `pending → running → retrying → running → completed`, terminal failure and restart persistence;
- duplicate submissions proving one job ID / one persisted job row / one execution;
- current markers `A9_CORRELATED_LIFECYCLE_GATE=PASS` and `A9_IDEMPOTENCY_RETRY_RESTART_GATE=PASS`.

See `REQUIREMENTS_AUDIT.md`, `VERIFICATION_EVIDENCE.md`, and `SOURCE_GAP_AND_ASSUMPTIONS.md` for the recovered-S3 mapping, evidence details and implementation-choice boundary.

Recovered S3 currently defines no separate explicit S4 prompt/rematch exercise for Assignment 9.
