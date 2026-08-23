from __future__ import annotations

import os
from pathlib import Path


ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ARTIFACT_ROOT / "data" / "jobs.sqlite3"
DB_PATH = Path(os.getenv("JOB_DB_PATH", str(DEFAULT_DB_PATH)))
MAX_ATTEMPTS = int(os.getenv("JOB_MAX_ATTEMPTS", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("JOB_RETRY_DELAY_SECONDS", "0.35"))
STALE_RUNNING_SECONDS = float(os.getenv("JOB_STALE_RUNNING_SECONDS", "30"))
WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "0.1"))
# Disabled by default. The isolated verification harness enables this briefly
# so a genuinely running job can be observed through the status endpoint.
EXECUTION_HOLD_SECONDS = float(os.getenv("JOB_EXECUTION_HOLD_SECONDS", "0"))