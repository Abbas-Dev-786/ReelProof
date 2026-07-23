from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from ..jobs.store import create_job, get_job
from ..jobs.worker import drop_queue, get_queue, launch_worker
from ..schemas import (
    CampaignResult,
    CreateCampaignRequest,
    CreateCampaignResponse,
    JobStatus,
    RenderMode,
    VerifyResponse,
)
from ..storage import verify_run

router = APIRouter()


@router.post("/campaigns", response_model=CreateCampaignResponse)
async def create_campaign(req: CreateCampaignRequest) -> CreateCampaignResponse:
    job_id = str(uuid.uuid4())
    create_job(job_id, req.topic, req.mode.value)

    loop = asyncio.get_event_loop()
    launch_worker(job_id, req.topic, req.mode, req.beat_count, loop)

    return CreateCampaignResponse(job_id=job_id)


@router.get("/campaigns/{job_id}/stream")
async def stream_campaign(job_id: str) -> StreamingResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_gen() -> AsyncGenerator[str, None]:
        queue = get_queue(job_id)
        try:
            while True:
                payload = await asyncio.wait_for(queue.get(), timeout=30)
                if payload is None:  # sentinel = engine finished
                    yield "event: done\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.TimeoutError:
            yield "event: heartbeat\ndata: {}\n\n"
        finally:
            drop_queue(job_id)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/campaigns/{job_id}", response_model=CampaignResult)
async def get_campaign(job_id: str) -> CampaignResult:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] == "done" and job.get("result"):
        return CampaignResult(**job["result"])

    return CampaignResult(
        job_id=job_id,
        topic=job.get("topic", ""),
        mode=RenderMode(job.get("mode", "slideshow")),
        status=JobStatus(job["status"]),
        error=job.get("error"),
    )


@router.get("/verify/{run_id}", response_model=VerifyResponse)
async def verify(run_id: str) -> VerifyResponse:
    info = verify_run(run_id)
    return VerifyResponse(
        run_id=run_id,
        verified=info.get("verified", False),
        manifest_hash=info.get("manifest_hash"),
        provider=info.get("provider"),
        model=info.get("model"),
        created_at=info.get("created_at"),
    )
