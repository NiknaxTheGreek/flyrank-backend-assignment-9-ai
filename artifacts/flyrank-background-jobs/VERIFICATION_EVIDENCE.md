# Verification evidence

The initial checkpoint was strengthened on 2026-08-23 with an isolated, correlated FastAPI-and-worker runtime trace. It records direct API status observations, structured process logs, process IDs, a SQLite query snapshot, and fresh automated-check transcripts under `verification/`.

## Evidence locations

- `verification/e2e-observations.json`
- `verification/api-e2e.log` and `verification/api.log`
- `verification/worker-e2e.log` and `verification/worker.log`
- `verification/database-snapshot.json`
- `verification/correlated-runtime-observations.json` — strongest lifecycle proof; includes API/worker process IDs, direct `running` observations, and restart persistence.
- `verification/correlated-api.log` and `verification/correlated-worker.log` — correlated JSON lifecycle events by job ID and process ID.
- `verification/correlated-runtime-database-snapshot.json`
- `verification/workspace-typecheck.txt`
- `verification/python-test-results.txt`

## Completed checkpoints

1. A normal job returned `202`, was observed as `pending` with attempt count `0`, then completed and returned a text-analysis result.
2. Two submissions with one `Idempotency-Key` returned the same identifier; the persisted matching-job count was `1`, and its completed execution count in the database snapshot was `1`.
3. `transient` was observed as `retrying` at attempt `1`, then completed at attempt `2`.
4. `permanent` reached terminal `failed` at attempt `3` and returned the documented `409` result-not-available response.
5. Both API and worker were restarted; the completed job and result remained available with `persistenceVerified: true`.

## Correlated runtime trace

The current evidence bundle is the authoritative acceptance trace:

1. An isolated FastAPI process accepted the recorded transient job with HTTP `202` while it was `pending`.
2. A separate worker process claimed that exact ID, emitted `running`, scheduled a controlled transient retry, claimed it again, then completed it. The direct status observations preserve `pending → running → retrying → running → completed`; the result endpoint returned `200`.
3. A separate persistent-failure job was directly observed as `running`, `retrying`, then terminal `failed` at attempt 3; its result endpoint returned `409`.
4. The recorded API and worker PIDs are distinct, then both change after a controlled restart. The completed transient job's status and result remained available after restart.
5. `correlated-api.log` records `api_started` and `job_accepted`; `correlated-worker.log` records `worker_started`, `job_claimed`, `job_execution_started`, retry scheduling, completion, and terminal failure. Each event includes the same job ID and worker process ID.

The evidence harness sets `JOB_EXECUTION_HOLD_SECONDS=0.45` only inside its isolated processes, solely to make the otherwise fast real `running` state observable. Normal application behavior retains the default value of `0`.

## Automated checks

- Frontend and full workspace TypeScript checks: passed; exact transcript in `verification/workspace-typecheck.txt`.
- Python lifecycle suite: `10 passed, 1 warning in 4.27s`; exact transcript in `verification/python-test-results.txt`.

Human-vs-AI rematch comparison remains pending until a human version is supplied.