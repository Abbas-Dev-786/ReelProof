from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from genblaze_core import Asset, Modality, Pipeline
from genblaze_core.models.step import Step
from genblaze_core.providers import per_unit
from genblaze_gmicloud import GMICloudImageProvider, GMICloudVideoProvider

from ..config import settings
from ..schemas import Beat


def _image_provider() -> GMICloudImageProvider:
    provider = GMICloudImageProvider(api_key=settings.gmi_api_key or None)
    provider.models.register_pricing(
        settings.gmi_image_model, per_unit(settings.gmi_image_unit_cost_usd)
    )
    provider.models.register_pricing(
        settings.gmi_product_image_model,
        per_unit(settings.gmi_product_image_unit_cost_usd),
    )
    return provider


def _video_provider() -> GMICloudVideoProvider:
    provider = GMICloudVideoProvider(api_key=settings.gmi_api_key or None)
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


def render_beat_image(
    beat: Beat,
    style_suffix: str = "",
    product_assets: Sequence[Asset] | None = None,
) -> str:
    """Generate one still image for a beat. Returns the asset URL."""
    if not settings.gmi_api_key:
        raise RuntimeError("GMI_API_KEY is required to render slideshow beats")

    settings.output_path.mkdir(parents=True, exist_ok=True)

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

    result = (
        Pipeline(f"beat-{beat.index}-image")
        .step(
            provider,
            model=settings.gmi_product_image_model if product_input else settings.gmi_image_model,
            prompt=prompt,
            modality=Modality.IMAGE,
            aspect_ratio="9:16",
            external_inputs=product_input or None,
            fallback_models=["gemini-2.5-flash-image"],
        )
        .run(timeout=120)
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

    product_input = list(product_assets or [])[:1]
    image_asset: Asset | None = None
    video_step_id: str | None = None

    def on_step_complete(event: Any) -> None:
        nonlocal image_asset
        if event.step_index == 0 and event.step.assets:
            image_asset = event.step.assets[0]

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
        Pipeline(f"pov-beat-{job_id}-{beat.index}", chain=True)
        .step(
            _image_provider(),
            model=settings.gmi_product_image_model if product_input else settings.gmi_image_model,
            prompt=_pov_image_prompt(beat, style_suffix, bool(product_input)),
            modality=Modality.IMAGE,
            aspect_ratio="9:16",
            external_inputs=product_input or None,
            fallback_models=["gemini-2.5-flash-image"],
            metadata={"job_id": job_id, "beat_index": beat.index, "render_mode": "pov"},
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
            on_step_complete=on_step_complete,
        )
    )

    steps = result.run.steps
    if len(steps) != 2 or not steps[0].assets or not steps[1].assets:
        raise RuntimeError(f"Beat {beat.index}: image-to-video generation returned incomplete assets")

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


async def resume_pov_video(checkpoint: dict[str, Any]) -> POVBeatRender:
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

    return POVBeatRender(
        image_url=str(source_asset.url),
        video_url=str(completed.assets[0].url),
        cost_usd=completed.cost_usd or 0.0,
    )
