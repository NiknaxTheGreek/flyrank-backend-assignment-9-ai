# Assignment 9 verification evidence

The strongest current checkpoint is GitHub Actions run `32712518867` on 2026-08-24. It executed the current repository code from a clean checkout rather than relying only on previously committed evidence files.

## Current GitHub Actions checkpoint

The run passed:

1. clean repository installation with `python -m pip install .`;
2. backend compilation;
3. **10 Python lifecycle tests**;
4. an isolated real FastAPI process plus a distinct real worker process;
5. a correlated transient lifecycle observed as `pending → running → retrying → running → completed` with result HTTP `200`;
6. a persistent retryable failure that exhausted three attempts, became `failed`, retained `lastError`, and returned result-not-available HTTP `409`;
7. API/worker restart with the completed result still available;
8. duplicate submissions using the same `Idempotency-Key` returning the same job ID;
9. exactly one persisted matching job row and one execution for that idempotent submission;
10. current runtime evidence uploaded as the `assignment-9-background-job-evidence` Actions artifact.

The workflow printed both acceptance markers:

```text
A9_CORRELATED_LIFECYCLE_GATE=PASS
A9_IDEMPOTENCY_RETRY_RESTART_GATE=PASS
```

## Repository evidence locations

The project also retains the earlier reproducible evidence harnesses and captured outputs under `verification/`, including:

- `correlated_runtime_trace.py` — launches its own API and worker processes against an isolated SQLite database, records process IDs and lifecycle observations, and verifies restart persistence;
- `correlated-runtime-observations.json`;
- `correlated-runtime-database-snapshot.json`;
- `correlated-api.log` and `correlated-worker.log`;
- `e2e_checkpoint.py` — exercises normal completion, duplicate submission, transient retry, persistent failure and restart verification;
- `e2e-observations.json`;
- `database-snapshot.json`;
- `python-test-results.txt` and `workspace-typecheck.txt` from the earlier environment.

## What the evidence proves against recovered S3

- **202 Accepted:** the API accepts work before completion and returns a job ID.
- **Background execution:** the API and worker are independent processes; the worker performs the operation outside the HTTP request lifecycle.
- **Status/result:** clients can inspect persisted state and retrieve completed output.
- **Idempotency:** duplicate submissions with one key resolve to one persisted job; completion-side-effect protection is also tested.
- **Retries:** transient failure is retried and succeeds; persistent retryable failure exhausts the bounded budget.
- **Observability:** failed state, attempt count, `lastError`, job ID and structured worker lifecycle events remain inspectable.
- **Persistence:** a completed job/result survives API and worker process restart.

The test harness may set a short `JOB_EXECUTION_HOLD_SECONDS` only to make the otherwise fast real `running` state observable. Normal application behavior keeps the default at `0`.

Recovered S3 currently defines no separate explicit S4 prompt/rematch exercise for Assignment 9.
