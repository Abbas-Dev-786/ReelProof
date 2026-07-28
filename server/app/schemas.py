from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RenderMode(StrEnum):
    slideshow = "slideshow"
    pov = "pov"


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


# --- Beat planner ---


class Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    concept: str  # visual concept for image generation
    caption: str  # on-screen text (burned in via ffmpeg)
    vo: str | None = None  # optional voiceover line


class BeatPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: str
    beats: list[Beat]
    suggested_caption: str
    hashtags: list[str]


# --- API requests / responses ---


class CreateCampaignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=3, max_length=500)
    mode: RenderMode = RenderMode.slideshow
    beat_count: int = Field(default=5, ge=3, le=8)
    generate_music: bool = True
    start_immediately: bool = True

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("topic must contain at least 3 non-whitespace characters")
        return normalized


class CreateCampaignResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.pending


class ProductAssetResponse(BaseModel):
    asset_id: str
    filename: str
    media_type: str
    asset_url: str
    sha256: str | None = None
    run_id: str
    manifest_hash: str
    manifest_uri: str | None = None


class BeatResult(BaseModel):
    index: int
    image_url: str
    video_url: str | None = None
    captioned_url: str | None = None
    judge_score: float | None = None
    judge_iterations: int = 1
    passed: bool = True


class CampaignResult(BaseModel):
    job_id: str
    topic: str
    mode: RenderMode
    status: JobStatus
    generate_music: bool = True
    beat_plan: BeatPlan | None = None
    beats: list[BeatResult] = Field(default_factory=list)
    reel_url: str | None = None  # final 9:16 MP4 in B2
    music_url: str | None = None
    suggested_caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    manifest_hash: str | None = None
    manifest_uri: str | None = None
    run_id: str | None = None
    total_cost_usd: float | None = None
    error: str | None = None


class VerifyResponse(BaseModel):
    run_id: str
    verified: bool
    manifest_hash: str | None = None
    manifest_uri: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: str | None = None
    lineage: list[dict[str, Any]] = Field(default_factory=list)  # parent_run_id chain
    error: str | None = None


class LineageResponse(BaseModel):
    job_id: str
    runs: list[dict[str, Any]] = Field(default_factory=list)


class CampaignPackageResponse(BaseModel):
    """Durable campaign hand-off: result, uploaded products, and manifests."""

    job_id: str
    campaign: CampaignResult
    product_assets: list[ProductAssetResponse] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class StreamEventPayload(BaseModel):
    """Wire-safe SSE payload (no in-process Step/Result objects)."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)
