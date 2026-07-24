from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from genblaze_core import Asset

from app.api.routes import router
from app.config import settings
from app.jobs.store import (
    claim_job_start,
    init_db,
    list_product_assets,
    recoverable_jobs,
    requeue_expired_jobs,
)
from app.jobs.worker import WORKER_ID, launch_worker
from app.schemas import RenderMode


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    recovered_count = requeue_expired_jobs()
    if recovered_count:
        logging.getLogger(__name__).warning("Requeued abandoned campaign jobs", extra={"count": recovered_count})
    for job in recoverable_jobs():
        if not claim_job_start(job["job_id"], WORKER_ID, settings.job_lease_seconds):
            continue
        assets = [
            Asset(
                asset_id=row["asset_id"],
                url=row["asset_url"],
                media_type=row["media_type"],
                sha256=row["sha256"],
            )
            for row in list_product_assets(job["job_id"])
        ]
        launch_worker(
            job["job_id"],
            job["topic"],
            RenderMode(job["mode"]),
            job["beat_count"],
            product_assets=assets,
        )
    yield


app = FastAPI(title="ReelProof API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
