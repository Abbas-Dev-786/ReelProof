from __future__ import annotations

from typing import Any

from genblaze_core.providers import per_unit
from genblaze_core.providers.base import BaseProvider
from genblaze_gmicloud import GMICloudImageProvider

from ..config import settings
from .cloudflare_image import CloudflareImageProvider
from .safety import image_retry_policy


def image_provider() -> BaseProvider:
    if settings.image_provider == "cloudflare":
        return CloudflareImageProvider(
            account_id=settings.cloudflare_account_id,
            api_token=settings.cloudflare_api_token,
            output_dir=settings.output_path / "cloudflare-images",
            retry_policy=image_retry_policy(),
        )

    provider = GMICloudImageProvider(
        api_key=settings.gmi_api_key or None, retry_policy=image_retry_policy()
    )
    provider.models.register_pricing(
        settings.gmi_image_model, per_unit(settings.gmi_image_unit_cost_usd)
    )
    provider.models.register_pricing(
        settings.gmi_product_image_model,
        per_unit(settings.gmi_product_image_unit_cost_usd),
    )
    return provider


def image_model(*, has_product_input: bool) -> str:
    return settings.active_product_image_model if has_product_input else settings.active_image_model


def image_fallback_models(*, has_product_input: bool) -> list[str]:
    if settings.image_provider == "cloudflare":
        return []
    return (
        settings.gmi_product_image_fallback_model_list
        if has_product_input
        else settings.gmi_image_fallback_model_list
    )


def image_generation_params() -> dict[str, Any]:
    if settings.image_provider == "cloudflare":
        return {
            "width": settings.cloudflare_image_width,
            "height": settings.cloudflare_image_height,
            "num_steps": settings.cloudflare_image_num_steps,
            "guidance": settings.cloudflare_image_guidance,
        }
    return {"aspect_ratio": "9:16"}


def require_image_provider_credentials(context: str) -> None:
    if missing := settings.missing_image_provider_settings():
        raise RuntimeError(f"{', '.join(missing)} is required to {context}")
