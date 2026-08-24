# Assignment 9 recovered-S3 requirements audit

| S3 requirement | Current implementation/evidence | Status |
| --- | --- | --- |
| Move slow work outside HTTP request | `POST /api/jobs` persists work only; `backend.worker` executes it in a separate process | PASS |
| Immediate acceptance | Submission returns HTTP `202` with a job ID before worker completion | PASS |
| Job can be identified | Every accepted job has a persisted UUID | PASS |
| Status endpoint | `GET /api/jobs/{id}` exposes lifecycle state, attempts, timestamps and safe failure fields | PASS |
| Result can be retrieved | `GET /api/jobs/{id}/result` returns the result after completion and a controlled non-success response before/after failure | PASS |
| Durable state/result | SQLite persists jobs/results across API and worker restarts | PASS |
| Separate worker | `backend/worker.py` runs independently from the FastAPI process; current CI records distinct process IDs | PASS |
| Idempotency because jobs may run twice | unique `jobs.idempotency_key` deduplicates submission; unique `job_effects.job_id` protects completion effects | PASS |
| Retries because jobs will fail | retryable failures move to `retrying` with bounded attempts and increasing delay; persistent failure becomes terminal | PASS |
| Failure visibility / observability | persisted `failed` status, attempt count and `lastError` plus structured lifecycle logs make terminal failure visible | PASS |
| Restart/recovery behavior | stale `running` jobs are recovered to retryable state; completed result remains available after process restart | PASS |
| Automated verification | Python lifecycle suite plus current GitHub Actions S3 runtime gate | PASS |
| Documentation/repository clarity | root README plus detailed nested README, audit, assumptions and evidence docs | PASS |

## Current checkpoint

GitHub Actions run `32712518867` passed the current branch with:

- clean `pip install .` from the repository root;
- Python compilation;
- **10 lifecycle tests passed**;
- `A9_CORRELATED_LIFECYCLE_GATE=PASS` after a real API + separate-worker trace showing `pending → running → retrying → running → completed`, terminal failure and restart persistence;
- `A9_IDEMPOTENCY_RETRY_RESTART_GATE=PASS` after duplicate submissions returned the same job, one persisted job row executed once, retries were observed, terminal failure stayed visible, and a completed result survived API/worker restart.

## Technology boundary

Recovered S3 explicitly leaves queue provider, worker framework, route names, database schema, retry counts and alert provider unspecified. FastAPI, SQLite, polling, the exact status names and deterministic text analysis are therefore implementation choices rather than FlyRank-mandated details.

## S4 boundary

Recovered S3 records no separate explicit S4 prompt/rematch exercise for Assignment 9.
