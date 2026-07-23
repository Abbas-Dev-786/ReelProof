from __future__ import annotations

from collections.abc import Sequence

from genblaze_core import Asset, Modality, Pipeline
from genblaze_core.providers import per_unit
from genblaze_gmicloud import GMICloudImageProvider

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
