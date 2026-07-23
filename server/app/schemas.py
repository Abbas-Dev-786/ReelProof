from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RenderMode(str, Enum):
    slideshow = "slideshow"
    pov = "pov"



class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


# --- Beat planner ---

class Beat(BaseModel):
    index: int
    concept: str        # visual concept for image generation
    caption: str        # on-screen text (burned in via ffmpeg)
    vo: str | None = None  # optional voiceover line


class BeatPlan(BaseModel):
    hook: str
    beats: list[Beat]
    suggested_caption: str
    hashtags: list[str]


# --- API requests / responses ---

class CreateCampaignRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    mode: RenderMode = RenderMode.slideshow
    beat_count: int = Field(default=5, ge=3, le=8)


class CreateCampaignResponse(BaseModel):
    job_id: str


class BeatResult(BaseModel):
    index: int
    image_url: str
    captioned_url: str | None = None
    judge_score: float | None = None
    judge_iterations: int = 1
    passed: bool = True


class CampaignResult(BaseModel):
    job_id: str
    topic: str
    mode: RenderMode
    status: JobStatus
    beat_plan: BeatPlan | None = None
    beats: list[BeatResult] = []
    reel_url: str | None = None          # final 9:16 MP4 in B2
    music_url: str | None = None
    suggested_caption: str | None = None
    hashtags: list[str] = []
    manifest_hash: str | None = None
    run_id: str | None = None
    total_cost_usd: float | None = None
    error: str | None = None


class VerifyResponse(BaseModel):
    run_id: str
    verified: bool
    manifest_hash: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: str | None = None
    lineage: list[dict[str, Any]] = []   # parent_run_id chain


class StreamEventPayload(BaseModel):
    """Wire-safe SSE payload (no in-process Step/Result objects)."""
    type: str
    data: dict[str, Any] = {}
