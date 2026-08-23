# Source gap and implementation assumptions

## Recovered FlyRank requirements

The available request explicitly preserves these assignment requirements:

- A durable request → accepted job → separate worker → status/result lifecycle.
- SQLite persistence, retries, idempotency, observable failures, and controlled failure modes.
- HTTP 202 acceptance before completion, status/result endpoints, and automated/E2E verification.
- No comparison with the separate human Assignment 9 implementation until it exists.

## Source boundary

The original full S3 assignment brief is not available in this chat. This project did **not** inspect, copy, compare with, or infer requirements from any separate human Assignment 9 implementation.

## Documented implementation assumptions

1. **Endpoint shape:** `/api/jobs` plus conventional status/result endpoints are used because the preserved request did not provide a required route naming scheme.
2. **Idempotency transport:** `Idempotency-Key` is required as an HTTP header and unique in SQLite.
3. **Attempt budget:** the default is three total attempts, configurable by `JOB_MAX_ATTEMPTS`.
4. **Failure modes:** `transient` fails once then succeeds; `permanent` models a repeatedly retryable outage and demonstrates eventual terminal failure after the bounded budget.
5. **Recovery model:** a single-node worker uses a `claimed_at` lease. Jobs stale for `JOB_STALE_RUNNING_SECONDS` become retryable on worker startup.
6. **Business operation:** text analysis is intentionally small and deterministic so job-system semantics remain the assignment focus.
7. **No external queue:** SQLite is the durable queue and is suitable for this single-node demonstration, not a multi-node production queue.

No additional mandatory product features are assumed.