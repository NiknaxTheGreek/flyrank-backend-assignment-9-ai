# Recovered S3 boundary and implementation assumptions

## Authoritative FlyRank requirements now available

The recovered S3 Assignment 9 source is now the acceptance baseline. It requires the conceptual lifecycle:

```text
client submits work → API returns 202 Accepted → worker executes outside the request lifecycle → persisted status/result can be queried
```

It also explicitly requires the three reliability realities:

1. jobs may run twice → design for idempotency;
2. jobs will fail → implement retries;
3. someone must know → keep failures visible/observable.

S3 does **not** prescribe the queue provider, worker framework, route names, status vocabulary, database schema, retry count, alert provider, or exact slow operation. Assignment 6's LLM call is suggested as a candidate, not mandated.

## Local implementation choices

1. **Business operation:** deterministic text analysis keeps the assignment focused on job mechanics rather than external-provider variability.
2. **API shape:** `/api/jobs`, `/api/jobs/{id}`, and `/api/jobs/{id}/result` are local route choices.
3. **Persistence/queue:** SQLite stores both durable job state and queue timing for this single-node demonstration.
4. **Idempotency transport:** callers supply `Idempotency-Key`; the database enforces uniqueness and repeated submissions return the original job.
5. **Side-effect idempotency:** `job_effects.job_id` is unique and completion uses an idempotent insert so a repeated worker execution does not duplicate the completion effect.
6. **Retry budget:** three total attempts by default, configurable through `JOB_MAX_ATTEMPTS`.
7. **Failure modes:** `transient` fails once then succeeds; `permanent` simulates a repeatedly retryable dependency outage until the bounded retry budget is exhausted.
8. **Recovery model:** stale `running` work is returned to `retrying` on worker startup using a single-node SQLite lease assumption.
9. **Observability:** structured API/worker lifecycle logs plus persisted status, attempts and `lastError` make failures inspectable without logging the submitted text or idempotency key.

## S4 boundary

Recovered S3 states that Assignments 8 and 9 currently have **no separate explicit S4 prompt/rematch exercise**. No additional Assignment 9 AI Rematch is claimed or required from the currently available source.
