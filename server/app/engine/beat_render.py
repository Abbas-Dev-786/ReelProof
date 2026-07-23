from __future__ import annotations

import os

from genblaze_core import Modality, Pipeline
from genblaze_gmicloud import GMICloudImageProvider

from ..config import settings
from ..schemas import Beat


def _image_provider() -> GMICloudImageProvider:
    return GMICloudImageProvider(api_key=settings.gmi_api_key or None)


def render_beat_image(beat: Beat, style_suffix: str = "") -> str:
    """Generate one still image for a beat. Returns the asset URL."""
    os.makedirs(settings.output_dir, exist_ok=True)

    prompt = beat.concept
    if style_suffix:
        prompt = f"{prompt}. {style_suffix}"

    provider = _image_provider()

    result = (
        Pipeline(f"beat-{beat.index}-image")
        .step(
            provider,
            model="reve-create",
            prompt=prompt,
            modality=Modality.IMAGE,
            fallback_models=["gemini-2.5-flash-image"],
        )
        .run(timeout=120)
    )

    steps = result.run.steps
    if not steps or not steps[0].assets:
        raise RuntimeError(f"Beat {beat.index}: image generation returned no assets")

    return steps[0].assets[0].url
