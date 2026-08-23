from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import DB_PATH
from .db import JobStore
from .logging import get_logger, log_event

logger = get_logger("flyrank.api")


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10_000)
    failureMode: Literal["none", "transient", "permanent"] = "none"

    @field_validator("text")
    @classmethod
    def text_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain non-whitespace characters")
        return value


def create_app(db_path: str | Path | None = None) -> FastAPI:
    store = JobStore(db_path or os.getenv("JOB_DB_PATH", str(DB_PATH)))
    store.initialize()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log_event(logger, "api_started", process_id=os.getpid(), role="api")
        yield

    app = FastAPI(
        title="FlyRank Background Jobs",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.store = store

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid request", "detail": jsonable_encoder(exc.errors())},
        )

    @app.get("/healthz", include_in_schema=False)
    @app.get("/api/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/jobs", status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
    @app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        payload: JobInput,
        idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    ) -> dict[str, object]:
        job, deduplicated = store.create_or_get(
            text=payload.text,
            failure_mode=payload.failureMode,
            idempotency_key=idempotency_key,
        )
        log_event(
            logger,
            "job_accepted",
            process_id=os.getpid(),
            job_id=job["id"],
            deduplicated=deduplicated,
            status=job["status"],
        )
        return {"jobId": job["id"], "status": job["status"], "deduplicated": deduplicated}

    @app.get("/jobs", include_in_schema=False)
    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, object]]:
        return store.list_recent()

    @app.get("/jobs/summary", include_in_schema=False)
    @app.get("/api/jobs/summary")
    def job_summary() -> dict[str, int]:
        return store.summary()

    @app.get("/jobs/{job_id}", include_in_schema=False)
    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        job = store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.get("/jobs/{job_id}/result", include_in_schema=False)
    @app.get("/api/jobs/{job_id}/result")
    def get_job_result(job_id: str) -> dict[str, object]:
        job = store.get_internal(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Job result is not available",
                    "status": job["status"],
                    "lastError": job["last_error"],
                },
            )
        return {"jobId": job["id"], "result": __import__("json").loads(job["result_json"])}

    return app


app = create_app()