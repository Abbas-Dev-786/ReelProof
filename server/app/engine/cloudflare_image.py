from __future__ import annotations

import base64
import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import Modality, ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers.base import (
    ProviderCapabilities,
    SyncProvider,
    validate_chain_input_url,
)
from genblaze_core.providers.model_registry import ModelRegistry, ModelSpec
from genblaze_core.runnable.config import RunnableConfig

_DEFAULT_BASE_URL = "https://api.cloudflare.com/client/v4"
_DEFAULT_MODELS = (
    "@cf/bytedance/stable-diffusion-xl-lightning",
    "@cf/stabilityai/stable-diffusion-xl-base-1.0",
    "@cf/lykon/dreamshaper-8-lcm",
    "@cf/runwayml/stable-diffusion-v1-5-img2img",
    "@cf/runwayml/stable-diffusion-v1-5-inpainting",
)
_PARAM_ALLOWLIST = frozenset(
    {
        "prompt",
        "negative_prompt",
        "width",
        "height",
        "num_steps",
        "strength",
        "guidance",
        "seed",
        "image",
        "image_b64",
        "mask",
        "mask_b64",
    }
)


def _registry() -> ModelRegistry:
    registry = ModelRegistry(
        fallback=ModelSpec(
            model_id="*",
            modality=Modality.IMAGE,
            param_allowlist=_PARAM_ALLOWLIST,
        )
    )
    for model in _DEFAULT_MODELS:
        registry.register(
            ModelSpec(
                model_id=model,
                modality=Modality.IMAGE,
                param_allowlist=_PARAM_ALLOWLIST,
            )
        )
    return registry


def _extension_for_media_type(media_type: str | None) -> str:
    if not media_type:
        return ".jpg"
    if media_type == "image/jpg":
        return ".jpg"
    return mimetypes.guess_extension(media_type.split(";", 1)[0].strip()) or ".jpg"


def _save_image(data: bytes, media_type: str | None, output_dir: Path) -> Asset:
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    resolved_media_type = media_type.split(";", 1)[0].strip() if media_type else "image/jpeg"
    path = (
        output_dir
        / f"cloudflare-image-{digest[:16]}{_extension_for_media_type(resolved_media_type)}"
    )
    path.write_bytes(data)
    return Asset(url=path.resolve().as_uri(), media_type=resolved_media_type)


class CloudflareImageProvider(SyncProvider):
    """GenBlaze provider for Cloudflare Workers AI text/image-to-image models."""

    name = "cloudflare-image"

    @classmethod
    def create_registry(cls) -> ModelRegistry:
        return _registry()

    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        base_url: str = _DEFAULT_BASE_URL,
        output_dir: Path | str | None = None,
        http_timeout: float = 120.0,
        http_client: httpx.Client | None = None,
        models: ModelRegistry | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(models=models, **kwargs)
        self._account_id = account_id
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._output_dir = Path(output_dir) if output_dir is not None else Path.cwd()
        self._client = http_client or httpx.Client(timeout=http_timeout)
        self._owns_client = http_client is None

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supported_modalities=[Modality.IMAGE],
            supported_inputs=["text", "image"],
            accepts_chain_input=True,
            output_formats=["image/jpeg", "image/png"],
            models=list(_DEFAULT_MODELS),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(self, step: Step, config: RunnableConfig | None = None) -> Step:
        if not self._account_id or not self._api_token:
            raise ProviderError(
                "Cloudflare image generation requires CLOUDFLARE_ACCOUNT_ID and "
                "CLOUDFLARE_API_TOKEN",
                error_code=ProviderErrorCode.AUTH_FAILURE,
            )

        payload = self.prepare_payload(step)
        if step.inputs and "image_b64" not in payload and "image" not in payload:
            payload["image_b64"] = base64.b64encode(self._read_input_asset(step.inputs[0])).decode(
                "ascii"
            )

        url = f"{self._base_url}/accounts/{self._account_id}/ai/run/{step.model}"
        try:
            response = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Cloudflare image generation timed out: {exc}",
                error_code=ProviderErrorCode.TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Cloudflare image generation transport failed: {exc}",
                error_code=ProviderErrorCode.UNKNOWN,
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            raise ProviderError(
                f"Cloudflare image auth failed ({response.status_code}): {response.text[:500]}",
                error_code=ProviderErrorCode.AUTH_FAILURE,
            )
        if response.status_code == 429:
            raise ProviderError(
                f"Cloudflare image rate limited: {response.text[:500]}",
                error_code=ProviderErrorCode.RATE_LIMIT,
            )
        if response.status_code >= 500:
            raise ProviderError(
                f"Cloudflare image server error ({response.status_code}): {response.text[:500]}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Cloudflare image request failed ({response.status_code}): {response.text[:500]}",
                error_code=ProviderErrorCode.INVALID_INPUT,
            )

        asset = self._asset_from_response(response)
        step.assets.append(asset)
        step.provider_payload = {
            "cloudflare": {
                "success": True,
                "model": step.model,
                "content_type": response.headers.get("content-type"),
            }
        }
        return step

    def _asset_from_response(self, response: httpx.Response) -> Asset:
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("image/"):
            return _save_image(response.content, content_type, self._output_dir)

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                "Cloudflare image response was neither image bytes nor JSON",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc

        image_b64, media_type = self._extract_base64_image(body)
        if image_b64 is None:
            raise ProviderError(
                "Cloudflare image response did not contain image bytes",
                error_code=ProviderErrorCode.SERVER_ERROR,
            )
        try:
            data = base64.b64decode(image_b64)
        except ValueError as exc:
            raise ProviderError(
                "Cloudflare image response contained invalid base64",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc
        return _save_image(data, media_type, self._output_dir)

    def _extract_base64_image(self, body: object) -> tuple[str | None, str | None]:
        if not isinstance(body, dict):
            return None, None

        candidate: object = body
        if isinstance(body.get("result"), dict):
            candidate = body["result"]

        if isinstance(candidate, dict):
            for key in ("image", "image_b64", "b64_json"):
                value = candidate.get(key)
                if isinstance(value, str):
                    return value, candidate.get("media_type") if isinstance(
                        candidate.get("media_type"), str
                    ) else "image/jpeg"
            data = candidate.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                value = data[0].get("b64_json") or data[0].get("image") or data[0].get("image_b64")
                if isinstance(value, str):
                    media_type = data[0].get("media_type")
                    return value, media_type if isinstance(media_type, str) else "image/jpeg"

        return None, None

    def _read_input_asset(self, asset: Asset) -> bytes:
        validate_chain_input_url(str(asset.url))
        parsed = urlparse(str(asset.url))
        if parsed.scheme == "file":
            return Path(unquote(parsed.path)).read_bytes()
        response = self._client.get(str(asset.url))
        response.raise_for_status()
        return response.content
