# FlyRank Backend Assignment 9 — First Background Job

A FastAPI + SQLite implementation of the recovered Assignment 9 portal contract:

```text
request → 202 Accepted → durable job → separate worker → status/result
```

The assignment focuses on moving slow work outside the HTTP request lifecycle and making the job system safe when work runs more than once, fails, or needs operational visibility.

## S3 requirements implemented

- `POST /api/jobs` accepts work promptly with HTTP `202` and a job ID.
- A separate worker process performs the operation outside the request lifecycle.
- Job state, attempts, errors and results are persisted in SQLite.
- `GET /api/jobs/{jobId}` exposes status.
- `GET /api/jobs/{jobId}/result` exposes the completed result.
- Duplicate submission is controlled with a unique `Idempotency-Key`.
- Completion side effects are independently protected by a unique job effect.
- Retryable failures use bounded retries and increasing delay.
- Terminal failures remain visible through persisted status/error fields and structured worker logs.
- Worker restart recovery returns stale `running` jobs to retryable work.

Exact route names, SQLite, retry counts and the deterministic text-analysis operation are implementation choices because the recovered S3 source does not prescribe them.

## Install

Python 3.12+:

```bash
python -m pip install .
```

## Run

Start the API:

```bash
python -m uvicorn backend.app:app \
  --app-dir artifacts/flyrank-background-jobs \
  --host 127.0.0.1 \
  --port 8000
```

Start the worker in a second terminal:

```bash
python -m backend.worker
```

Both processes must use the same `JOB_DB_PATH` when you override the default database path.

## Example

```bash
curl -i -X POST http://127.0.0.1:8000/api/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-001' \
  -d '{"text":"Analyze this in the background.","failureMode":"none"}'
```

Then inspect:

```text
GET /api/jobs/{jobId}
GET /api/jobs/{jobId}/result
```

## Verify

```bash
PYTHONPATH=artifacts/flyrank-background-jobs \
python -m pytest artifacts/flyrank-background-jobs/tests -q

python artifacts/flyrank-background-jobs/verification/correlated_runtime_trace.py
```

The repository's GitHub Actions acceptance gate also runs a real API + separate worker lifecycle, duplicate/idempotency checks, retries, terminal failure visibility and restart persistence.

Detailed implementation notes and evidence live under [`artifacts/flyrank-background-jobs/`](artifacts/flyrank-background-jobs/).

Assignments 8 and 9 currently have no separate explicit S4 prompt/rematch exercise in the recovered S3 source.
