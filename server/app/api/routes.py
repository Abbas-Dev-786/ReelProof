from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from genblaze_core import Asset
from PIL import Image, UnidentifiedImageError

from ..config import settings
from ..engine.ingest import ingest_product_image
from ..engine.safety import ContentSafetyError
from ..jobs.store import (
    claim_job_start,
    create_job,
    events_after,
    get_job,
    get_provenance,
    lineage_for_job,
    lineage_for_run,
    list_product_assets,
    record_product_asset,
    record_provenance,
)
from ..jobs.worker import WORKER_ID, launch_worker
from ..schemas import (
    CampaignPackageResponse,
    CampaignResult,
    CreateCampaignRequest,
    CreateCampaignResponse,
    JobStatus,
    LineageResponse,
    ProductAssetResponse,
    RenderMode,
    VerifyResponse,
)
from ..storage import verify_manifest_json

router = APIRouter()
logger = logging.getLogger(__name__)

_SUPPORTED_IMAGE_TYPES = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


@router.post("/campaigns", response_model=CreateCampaignResponse)
async def create_campaign(req: CreateCampaignRequest) -> CreateCampaignResponse:
    job_id = str(uuid.uuid4())
    create_job(job_id, req.topic, req.mode.value, req.beat_count)

    if req.start_immediately:
        _start_job(job_id)

    return CreateCampaignResponse(
        job_id=job_id, status=JobStatus.running if req.start_immediately else JobStatus.pending
    )


def _start_job(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not claim_job_start(job_id, WORKER_ID, settings.job_lease_seconds):
        raise HTTPException(
            status_code=409, detail=f"Job cannot be started from status {job['status']}"
        )

    assets = [
        Asset(
            asset_id=row["asset_id"],
            url=row["asset_url"],
            media_type=row["media_type"],
            sha256=row["sha256"],
        )
        for row in list_product_assets(job_id)
    ]
    launch_worker(
        job_id,
        job["topic"],
        RenderMode(job["mode"]),
        job["beat_count"],
        product_assets=assets,
    )


@router.post("/campaigns/{job_id}/start", response_model=CreateCampaignResponse)
async def start_campaign(job_id: str) -> CreateCampaignResponse:
    _start_job(job_id)
    return CreateCampaignResponse(job_id=job_id, status=JobStatus.running)


@router.post(
    "/campaigns/{job_id}/assets",
    response_model=ProductAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_product_asset(
    job_id: str, file: Annotated[UploadFile, File(...)]
) -> ProductAssetResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != JobStatus.pending.value:
        raise HTTPException(
            status_code=409, detail="Upload product images before starting the campaign"
        )
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(
            status_code=415, detail="Only JPEG, PNG, and WebP uploads are supported"
        )

    filename = Path(file.filename or "product-image").name[:255]
    asset_id = str(uuid.uuid4())
    upload_dir = settings.output_path / "uploads" / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    staged_path = upload_dir / f"{asset_id}.upload"

    try:
        total_bytes = 0
        with staged_path.open("wb") as staged:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Upload exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit",
                    )
                staged.write(chunk)
        if total_bytes == 0:
            raise HTTPException(status_code=422, detail="Uploaded image is empty")

        try:
            with Image.open(staged_path) as image:
                image.verify()
            with Image.open(staged_path) as image:
                width, height = image.size
                if width * height > settings.max_upload_pixels:
                    raise HTTPException(
                        status_code=422, detail="Image dimensions exceed the allowed limit"
                    )
                detected = _SUPPORTED_IMAGE_TYPES.get(image.format or "")
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(
                status_code=422, detail="Uploaded file is not a valid image"
            ) from exc

        if detected is None:
            raise HTTPException(
                status_code=415, detail="Only JPEG, PNG, and WebP uploads are supported"
            )

        media_type, suffix = detected
        normalized_filename = f"{Path(filename).stem[:200]}{suffix}"
        normalized_path = staged_path.with_suffix(suffix)
        staged_path.replace(normalized_path)
        staged_path = normalized_path

        try:
            ingested = await asyncio.to_thread(
                ingest_product_image,
                local_path=staged_path,
                filename=normalized_filename,
                media_type=media_type,
                job_id=job_id,
            )
        except ContentSafetyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Product image ingestion failed", extra={"job_id": job_id})
            raise HTTPException(
                status_code=502, detail="Product image could not be stored"
            ) from exc
        record_provenance(
            job_id=job_id,
            run_id=str(ingested["run_id"]),
            manifest_json=str(ingested["manifest_json"]),
            manifest_hash=str(ingested["manifest_hash"]),
            manifest_uri=ingested["manifest_uri"],
            parent_run_id=ingested["parent_run_id"],
        )
        record_product_asset(
            asset_id=str(ingested["asset_id"]),
            job_id=job_id,
            filename=normalized_filename,
            media_type=media_type,
            asset_url=str(ingested["asset_url"]),
            sha256=ingested["sha256"],
            run_id=str(ingested["run_id"]),
            manifest_hash=str(ingested["manifest_hash"]),
            manifest_uri=ingested["manifest_uri"],
        )
        return ProductAssetResponse(
            asset_id=str(ingested["asset_id"]),
            filename=normalized_filename,
            media_type=media_type,
            asset_url=str(ingested["asset_url"]),
            sha256=ingested["sha256"],
            run_id=str(ingested["run_id"]),
            manifest_hash=str(ingested["manifest_hash"]),
            manifest_uri=ingested["manifest_uri"],
        )
    finally:
        await file.close()
        staged_path.unlink(missing_ok=True)


@router.get("/campaigns/{job_id}/stream")
async def stream_campaign(
    job_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_gen() -> AsyncGenerator[str, None]:
        cursor = after
        if last_event_id:
            try:
                cursor = max(cursor, int(last_event_id))
            except ValueError:
                logger.warning("Ignoring invalid Last-Event-ID", extra={"job_id": job_id})
        while True:
            events = events_after(job_id, cursor)
            for event in events:
                cursor = int(event["event_id"])
                payload = {"type": event["type"], **event["data"]}
                yield f"id: {cursor}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
            current = get_job(job_id)
            if current and current["status"] in {JobStatus.done.value, JobStatus.failed.value}:
                yield "event: done\ndata: {}\n\n"
                break
            if not events:
                yield "event: heartbeat\ndata: {}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@router.get("/campaigns/{job_id}/package", response_model=CampaignPackageResponse)
async def campaign_package(job_id: str) -> CampaignPackageResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    campaign = await get_campaign(job_id)
    product_assets = [
        ProductAssetResponse(
            asset_id=asset["asset_id"],
            filename=asset["filename"],
            media_type=asset["media_type"],
            asset_url=asset["asset_url"],
            sha256=asset["sha256"],
            run_id=asset["run_id"],
            manifest_hash=asset["manifest_hash"],
            manifest_uri=asset["manifest_uri"],
        )
        for asset in list_product_assets(job_id)
    ]
    return CampaignPackageResponse(
        job_id=job_id,
        campaign=campaign,
        product_assets=product_assets,
        provenance=lineage_for_job(job_id),
    )


@router.get("/verify/{run_id}", response_model=VerifyResponse)
async def verify(run_id: str) -> VerifyResponse:
    record = get_provenance(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Provenance record not found")

    info = verify_manifest_json(record["manifest_json"])
    return VerifyResponse(
        run_id=run_id,
        verified=info.get("verified", False),
        manifest_hash=info.get("manifest_hash"),
        manifest_uri=info.get("manifest_uri"),
        provider=info.get("provider"),
        model=info.get("model"),
        created_at=info.get("created_at"),
        lineage=lineage_for_run(run_id),
        error=info.get("error"),
    )


@router.get("/campaigns/{job_id}/lineage", response_model=LineageResponse)
async def campaign_lineage(job_id: str) -> LineageResponse:
    if get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return LineageResponse(job_id=job_id, runs=lineage_for_job(job_id))
