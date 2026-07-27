from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genblaze_core import Modality, ObjectStorageSink, Pipeline
from genblaze_elevenlabs import ElevenLabsTTSProvider

from ..config import settings
from ..observability import langsmith_tracer
from ..workspace import require_media_workspace
from .safety import audio_retry_policy, moderation_hook
from .stability_audio import StabilityAudioProvider


@dataclass(frozen=True)
class GeneratedAudio:
    """A generated audio asset together with its immutable provenance."""

    url: str
    run_id: str | None = None
    manifest_json: str | None = None
    manifest_hash: str | None = None
    manifest_uri: str | None = None
    parent_run_id: str | None = None
    cost_usd: float = 0.0


def _audio_result(result: Any) -> GeneratedAudio:
    steps = result.run.steps
    if not steps or not steps[0].assets:
        raise RuntimeError("Audio generation returned no assets")
    return GeneratedAudio(
        url=str(steps[0].assets[0].url),
        run_id=result.run.run_id,
        manifest_json=result.manifest.model_dump_json(),
        manifest_hash=result.manifest.canonical_hash,
        manifest_uri=result.manifest.manifest_uri,
        parent_run_id=result.run.parent_run_id,
        cost_usd=sum(step.cost_usd or 0.0 for step in steps),
    )


def generate_music_asset(
    topic: str,
    duration_sec: float = 20.0,
    *,
    sink: ObjectStorageSink | None = None,
    job_id: str | None = None,
) -> GeneratedAudio:
    """Generate background music for the reel. Returns asset URL."""
    if not settings.stability_api_key:
        raise RuntimeError("STABILITY_API_KEY is required to generate slideshow music")
    if duration_sec <= 0:
        raise ValueError("duration_sec must be greater than zero")

    provider = StabilityAudioProvider(
        api_key=settings.stability_api_key or None, retry_policy=audio_retry_policy()
    )

    result = (
        Pipeline("reel-music", moderation=moderation_hook(), tracer=langsmith_tracer())
        .step(
            provider,
            model="stable-audio-2.5",
            prompt=f"upbeat background music for a short-form social video about: {topic}. No vocals.",
            modality=Modality.AUDIO,
            duration=duration_sec,
            metadata={"job_id": job_id, "asset_kind": "music"} if job_id else None,
        )
        .run(sink=sink, timeout=180, max_retries=settings.audio_step_retries)
    )
    return _audio_result(result)


def generate_music(topic: str, duration_sec: float = 20.0) -> str:
    """Generate background music and return its URL (legacy convenience API)."""
    return generate_music_asset(topic, duration_sec).url


def generate_voiceover_asset(
    lines: Sequence[str],
    *,
    sink: ObjectStorageSink | None = None,
    job_id: str | None = None,
    output_dir: str | Path,
) -> GeneratedAudio | None:
    """Generate one campaign narration track when voiceover is enabled.

    The planner's optional per-beat lines are intentionally joined into one
    track so the final montage has a single, deterministic narration input.
    """
    script = " ".join(line.strip() for line in lines if line and line.strip())
    if not script:
        return None
    if not settings.voiceover_enabled:
        return None
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is required when VOICEOVER_ENABLED=true")

    target_dir = require_media_workspace(output_dir)
    provider = ElevenLabsTTSProvider(
        api_key=settings.elevenlabs_api_key,
        output_dir=target_dir,
        retry_policy=audio_retry_policy(),
    )
    result = (
        Pipeline("reel-voiceover", moderation=moderation_hook(), tracer=langsmith_tracer())
        .step(
            provider,
            model=settings.elevenlabs_voice_model,
            prompt=script,
            modality=Modality.AUDIO,
            voice_id=settings.elevenlabs_voice_id,
            output_format="mp3_44100_128",
            metadata={"job_id": job_id, "asset_kind": "voiceover"} if job_id else None,
        )
        .run(sink=sink, timeout=180, max_retries=settings.voiceover_step_retries)
    )
    return _audio_result(result)
