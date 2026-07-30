from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from genblaze_core import AgentContext, AgentLoop, Asset, Modality, Pipeline
from genblaze_core.models.step import Step
from genblaze_core.providers import per_unit
from genblaze_core.providers.base import BaseProvider
from genblaze_gmicloud import GMICloudVideoProvider

from ..config import settings
from ..observability import ingest_with_trace, langsmith_tracer
from ..schemas import Beat
from .images import (
    image_fallback_models,
    image_generation_params,
    image_model,
    image_provider,
    require_image_provider_credentials,
)
from .judge import VisionJudge
from .safety import ensure_assets_allowed, moderation_hook, video_retry_policy


def _image_provider() -> BaseProvider:
    return image_provider()


def _video_provider() -> GMICloudVideoProvider:
    provider = GMICloudVideoProvider(
        api_key=settings.gmi_api_key or None, retry_policy=video_retry_policy()
    )
    provider.models.register_pricing(
        settings.pov_video_model, per_unit(settings.pov_video_unit_cost_usd)
    )
    return provider


@dataclass(frozen=True)
class POVBeatRender:
    """Artifacts and provenance returned by one image-to-video beat render."""

    image_url: str
    video_url: str
    run_id: str | None = None
    manifest_json: str | None = None
    manifest_hash: str | None = None
    manifest_uri: str | None = None
    parent_run_id: str | None = None
    cost_usd: float = 0.0
    judge_score: float | None = None
    judge_iterations: int = 1
    passed: bool = True


def _persist_pov_source_image(asset: Asset, sink: Any) -> Asset:
    """Synchronously make an image-to-video source reachable by GMICloud.

    A Cloudflare image is a local ``file://`` asset. Pipeline sinks normally
    upload only after the full run finishes, which is too late for the next
    chained provider step and for a resumable video checkpoint. Persist it
    before submitting the remote video request.
    """
    if not hasattr(sink, "put_asset"):
        raise TypeError("POV image persistence requires an ObjectStorageSink")
    persisted = sink.put_asset(asset)
    if urlparse(str(persisted.url)).scheme != "https":
        raise RuntimeError("POV source image was not persisted to a durable HTTPS URL")
    return persisted


def _capture_pov_source_image(event: Any, sink: Any) -> Asset | None:
    """Persist and return the first pipeline step's source image asset."""
    if event.step_index != 0 or not event.step.assets:
        return None
    return _persist_pov_source_image(event.step.assets[0], sink)


def render_beat_image(
    beat: Beat,
    style_suffix: str = "",
    product_assets: Sequence[Asset] | None = None,
) -> str:
    """Generate one still image for a beat. Returns the asset URL."""
    require_image_provider_credentials("render slideshow beats")

    prompt = beat.concept
    product_input = list(product_assets or [])[:1]
    if product_input:
        prompt = (
            f"{prompt}. Feature the supplied product naturally and preserve its recognizable "
            "shape, label, and colors. Do not add readable text to the image."
        )
    if style_suffix:
        prompt = f"{prompt}. {style_suffix}"

    provider = _image_provider()
    fallback_models = image_fallback_models(has_product_input=bool(product_input))

    result = (
        Pipeline(
            f"beat-{beat.index}-image", moderation=moderation_hook(), tracer=langsmith_tracer()
        )
        .step(
            provider,
            model=image_model(has_product_input=bool(product_input)),
            prompt=prompt,
            modality=Modality.IMAGE,
            external_inputs=product_input or None,
            fallback_models=fallback_models,
            **image_generation_params(),
        )
        .run(timeout=120, max_retries=settings.image_step_retries)
    )

    steps = result.run.steps
    if not steps or not steps[0].assets:
        raise RuntimeError(f"Beat {beat.index}: image generation returned no assets")

    return str(steps[0].assets[0].url)


def _pov_image_prompt(beat: Beat, style_suffix: str, has_product: bool) -> str:
    prompt = (
        f"{beat.concept}. Vertical 9:16 first-person social-video establishing frame, "
        "cinematic natural lighting, realistic detail, no readable text."
    )
    if has_product:
        prompt += (
            " Feature the supplied product naturally and preserve its recognizable shape, "
            "label, and colors."
        )
    if style_suffix:
        prompt += f" {style_suffix}"
    return prompt


def _pov_motion_prompt(beat: Beat) -> str:
    return (
        f"Animate this scene for a first-person vertical social video: {beat.concept}. "
        "Use one deliberate, physically plausible camera movement, subtle subject motion, "
        "stable composition, and no cuts, overlays, subtitles, or generated text."
    )


async def render_pov_beat(
    beat: Beat,
    *,
    job_id: str,
    sink: Any,
    product_assets: Sequence[Asset] | None = None,
    style_suffix: str = "",
    on_video_submitted: Callable[[str, Any, dict[str, Any]], None] | None = None,
) -> POVBeatRender:
    """Render a POV beat as a single async image-to-video pipeline.

    The callback is invoked immediately after the upstream video request is
    accepted. Its payload contains only the data required to resume polling;
    provider credentials are intentionally never persisted.
    """
    if not settings.gmi_api_key:
        raise RuntimeError("GMI_API_KEY is required to render POV beats")
    require_image_provider_credentials("render POV beat images")

    product_input = list(product_assets or [])[:1]
    image_asset: Asset | None = None
    video_step_id: str | None = None

    def on_step_complete(event: Any) -> None:
        nonlocal image_asset
        image_asset = _capture_pov_source_image(event, sink) or image_asset

    def on_submit(step_id: str, prediction_id: Any) -> None:
        nonlocal video_step_id
        # The first request creates the source still. Only a submitted video
        # can be resumed independently because its image input is now durable.
        if image_asset is None:
            return
        video_step_id = step_id
        if on_video_submitted:
            on_video_submitted(
                step_id,
                prediction_id,
                {
                    "kind": "pov-video",
                    "beat_index": beat.index,
                    "model": settings.pov_video_model,
                    "prompt": _pov_motion_prompt(beat),
                    "duration": settings.pov_clip_duration_sec,
                    "aspect_ratio": "9:16",
                    "source_asset": image_asset.model_dump(mode="json"),
                },
            )

    result = await (
        Pipeline(
            f"pov-beat-{job_id}-{beat.index}",
            chain=True,
            moderation=moderation_hook(),
            tracer=langsmith_tracer(),
        )
        .step(
            _image_provider(),
            model=image_model(has_product_input=bool(product_input)),
            prompt=_pov_image_prompt(beat, style_suffix, bool(product_input)),
            modality=Modality.IMAGE,
            external_inputs=product_input or None,
            fallback_models=image_fallback_models(has_product_input=bool(product_input)),
            metadata={"job_id": job_id, "beat_index": beat.index, "render_mode": "pov"},
            **image_generation_params(),
        )
        .step(
            _video_provider(),
            model=settings.pov_video_model,
            prompt=_pov_motion_prompt(beat),
            modality=Modality.VIDEO,
            duration=settings.pov_clip_duration_sec,
            aspect_ratio="9:16",
            fallback_models=settings.pov_video_fallback_model_list,
            metadata={"job_id": job_id, "beat_index": beat.index, "render_mode": "pov"},
        )
        .config({"on_submit": on_submit})
        .arun(
            sink=sink,
            timeout=settings.pov_pipeline_timeout_sec,
            pipeline_timeout=settings.pov_pipeline_timeout_sec,
            max_retries=settings.video_step_retries,
            on_step_complete=on_step_complete,
        )
    )

    steps = result.run.steps
    if len(steps) != 2 or not steps[0].assets or not steps[1].assets:
        raise RuntimeError(
            f"Beat {beat.index}: image-to-video generation returned incomplete assets"
        )

    if video_step_id is None:
        raise RuntimeError(f"Beat {beat.index}: video generation was not checkpointed")

    return POVBeatRender(
        image_url=str(steps[0].assets[0].url),
        video_url=str(steps[1].assets[0].url),
        run_id=result.run.run_id,
        manifest_json=result.manifest.model_dump_json(),
        manifest_hash=result.manifest.canonical_hash,
        manifest_uri=result.manifest.manifest_uri,
        parent_run_id=result.run.parent_run_id,
        cost_usd=sum(step.cost_usd or 0.0 for step in steps),
    )


async def run_pov_beat_loop(
    beat: Beat,
    *,
    job_id: str,
    sink: Any,
    product_assets: Sequence[Asset] | None = None,
    on_video_submitted: Callable[[str, Any, dict[str, Any]], None] | None = None,
    on_iteration: Callable[[dict[str, Any]], None] | None = None,
) -> POVBeatRender:
    """Run image-to-video generation through the same bounded quality loop as stills."""
    if not settings.gmi_api_key:
        raise RuntimeError("GMI_API_KEY is required to render POV beats")
    require_image_provider_credentials("render POV beat images")

    product_input = list(product_assets or [])[:1]
    latest_image_asset: Asset | None = None

    def on_step_complete(event: Any) -> None:
        nonlocal latest_image_asset
        latest_image_asset = _capture_pov_source_image(event, sink) or latest_image_asset

    def build_pipeline(ctx: AgentContext) -> Pipeline:
        feedback = ctx.last_evaluation.feedback if ctx.last_evaluation else ""

        def on_submit(step_id: str, prediction_id: Any) -> None:
            if latest_image_asset is None or on_video_submitted is None:
                return
            on_video_submitted(
                step_id,
                prediction_id,
                {
                    "kind": "pov-video",
                    "beat_index": beat.index,
                    "model": settings.pov_video_model,
                    "prompt": _pov_motion_prompt(beat),
                    "duration": settings.pov_clip_duration_sec,
                    "aspect_ratio": "9:16",
                    "source_asset": latest_image_asset.model_dump(mode="json"),
                },
            )

        style_suffix = feedback or ""
        return (
            Pipeline(
                f"pov-beat-{job_id}-{beat.index}-iter-{ctx.iteration}",
                chain=True,
                moderation=moderation_hook(),
            )
            .step(
                _image_provider(),
                model=image_model(has_product_input=bool(product_input)),
                prompt=_pov_image_prompt(beat, style_suffix, bool(product_input)),
                modality=Modality.IMAGE,
                external_inputs=product_input or None,
                fallback_models=image_fallback_models(has_product_input=bool(product_input)),
                metadata={"job_id": job_id, "beat_index": beat.index, "render_mode": "pov"},
                **image_generation_params(),
            )
            .step(
                _video_provider(),
                model=settings.pov_video_model,
                prompt=_pov_motion_prompt(beat),
                modality=Modality.VIDEO,
                duration=settings.pov_clip_duration_sec,
                aspect_ratio="9:16",
                fallback_models=settings.pov_video_fallback_model_list,
                metadata={"job_id": job_id, "beat_index": beat.index, "render_mode": "pov"},
            )
            .config({"on_submit": on_submit})
        )

    agent_result = await AgentLoop(
        build_pipeline,
        VisionJudge(),
        max_iterations=settings.max_agent_iterations,
        tracer=langsmith_tracer(),
    ).arun(
        sink=sink,
        timeout=settings.pov_pipeline_timeout_sec,
        pipeline_timeout=settings.pov_pipeline_timeout_sec,
        max_retries=settings.video_step_retries,
        on_step_complete=on_step_complete,
    )
    final = agent_result.final
    steps = final.run.steps
    if len(steps) != 2 or not steps[0].assets or not steps[1].assets:
        raise RuntimeError(f"Beat {beat.index}: image-to-video loop returned incomplete assets")

    if on_iteration:
        for iteration in agent_result.iterations:
            evaluation = iteration.evaluation
            on_iteration(
                {
                    "beat_index": beat.index,
                    "iteration": iteration.index,
                    "run_id": iteration.result.run.run_id,
                    "manifest_json": iteration.result.manifest.model_dump_json(),
                    "manifest_hash": iteration.result.manifest.canonical_hash,
                    "manifest_uri": iteration.result.manifest.manifest_uri,
                    "parent_run_id": iteration.result.run.parent_run_id,
                    "score": evaluation.score,
                    "passed": evaluation.passed,
                    "feedback": evaluation.feedback,
                }
            )
    final_evaluation = agent_result.iterations[-1].evaluation
    return POVBeatRender(
        image_url=str(steps[0].assets[0].url),
        video_url=str(steps[1].assets[0].url),
        run_id=final.run.run_id,
        manifest_json=final.manifest.model_dump_json(),
        manifest_hash=final.manifest.canonical_hash,
        manifest_uri=final.manifest.manifest_uri,
        parent_run_id=final.run.parent_run_id,
        cost_usd=agent_result.total_cost_usd,
        judge_score=final_evaluation.score,
        judge_iterations=len(agent_result.iterations),
        passed=agent_result.passed,
    )


async def resume_pov_video(checkpoint: dict[str, Any], *, sink: Any | None = None) -> POVBeatRender:
    """Resume polling a submitted POV video request without creating a second render."""
    payload = checkpoint["checkpoint"]
    if payload.get("kind") != "pov-video":
        raise ValueError("Checkpoint is not a resumable POV video request")

    source_asset = Asset.model_validate(payload["source_asset"])
    provider = _video_provider()
    step = Step(
        step_id=str(checkpoint["step_id"]),
        provider=provider.name,
        model=str(payload["model"]),
        modality=Modality.VIDEO,
        prompt=str(payload["prompt"]),
        params={
            "duration": int(payload["duration"]),
            "aspect_ratio": str(payload["aspect_ratio"]),
        },
        inputs=[source_asset],
        metadata={
            "job_id": checkpoint["job_id"],
            "beat_index": int(payload["beat_index"]),
            "render_mode": "pov",
            "resumed": True,
        },
    )
    completed = await provider.aresume(checkpoint["prediction_id"], step)
    if not completed.assets:
        raise RuntimeError("Resumed POV video generation returned no assets")

    video_asset = completed.assets[0]
    ensure_assets_allowed([video_asset])
    if sink is None:
        return POVBeatRender(
            image_url=str(source_asset.url),
            video_url=str(video_asset.url),
            cost_usd=completed.cost_usd or 0.0,
        )

    # aresume returns a provider asset outside the original Pipeline result.
    # Ingest it explicitly so recovery has the same immutable B2 evidence as a
    # normally completed image-to-video run.
    result = ingest_with_trace(
        assets=[video_asset],
        source="reelproof-pov-resume",
        source_metadata={
            "job_id": checkpoint["job_id"],
            "beat_index": int(payload["beat_index"]),
            "prediction_id": str(checkpoint["prediction_id"]),
            "source_image_url": str(source_asset.url),
        },
        sink=sink,
        name=f"pov-resume-{checkpoint['job_id']}-{payload['beat_index']}",
    )
    if not result.manifest.verify():
        raise RuntimeError("Resumed POV video manifest failed verification")

    return POVBeatRender(
        image_url=str(source_asset.url),
        video_url=str(result.run.steps[0].assets[0].url),
        run_id=result.run.run_id,
        manifest_json=result.manifest.model_dump_json(),
        manifest_hash=result.manifest.canonical_hash,
        manifest_uri=result.manifest.manifest_uri,
        parent_run_id=result.run.parent_run_id,
        cost_usd=completed.cost_usd or 0.0,
    )
