from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from genblaze_core import Asset, Modality
from genblaze_core.models.step import Step

from app.config import settings
from app.engine.beat_render import _image_provider, _video_provider
from app.engine.captions import caption_drawtext_filter
from app.engine.cloudflare_image import CloudflareImageProvider
from app.engine.images import image_generation_params, image_model
from app.engine.safety import ContentSafetyError, ensure_assets_allowed, ensure_prompt_allowed
from app.schemas import RenderMode
from app.workspace import media_workspace


class ReliabilityAndSafetyTests(unittest.TestCase):
    def test_image_and_video_providers_use_their_expected_retry_policies(self) -> None:
        self.assertEqual(_image_provider().retry_policy.max_attempts, 7)
        self.assertEqual(_video_provider().retry_policy.max_attempts, 2)

    def test_cloudflare_image_provider_is_selectable_for_still_images(self) -> None:
        prior = {
            "image_provider": settings.image_provider,
            "cloudflare_account_id": settings.cloudflare_account_id,
            "cloudflare_api_token": settings.cloudflare_api_token,
            "cloudflare_image_model": settings.cloudflare_image_model,
        }
        try:
            settings.image_provider = "cloudflare"
            settings.cloudflare_account_id = "test-account"
            settings.cloudflare_api_token = "test-token"
            settings.cloudflare_image_model = "@cf/bytedance/stable-diffusion-xl-lightning"

            with media_workspace() as workspace:
                provider = _image_provider()
                self.assertTrue(provider._output_dir.is_relative_to(workspace))
            self.assertEqual(provider.name, "cloudflare-image")
            self.assertEqual(image_model(has_product_input=False), settings.cloudflare_image_model)
            self.assertEqual(
                image_generation_params(),
                {"width": 768, "height": 1344, "num_steps": 8, "guidance": 7.5},
            )
        finally:
            for key, value in prior.items():
                setattr(settings, key, value)

    def test_cloudflare_slideshow_credentials_do_not_require_gmi_key(self) -> None:
        fields = (
            "image_provider",
            "cloudflare_account_id",
            "cloudflare_api_token",
            "gmi_api_key",
        )
        prior = {field: getattr(settings, field) for field in fields}
        try:
            settings.image_provider = "cloudflare"
            settings.cloudflare_account_id = "test-account"
            settings.cloudflare_api_token = "test-token"
            settings.gmi_api_key = ""

            self.assertNotIn(
                "GMI_API_KEY",
                settings.missing_campaign_settings(RenderMode.slideshow),
            )
            self.assertIn("GMI_API_KEY", settings.missing_campaign_settings(RenderMode.pov))
        finally:
            for key, value in prior.items():
                setattr(settings, key, value)

    def test_stability_key_is_not_required_when_background_music_is_disabled(self) -> None:
        fields = ("stability_api_key", "voiceover_enabled", "elevenlabs_api_key")
        prior = {field: getattr(settings, field) for field in fields}
        try:
            settings.stability_api_key = ""
            settings.voiceover_enabled = True
            settings.elevenlabs_api_key = ""

            missing = settings.missing_campaign_settings(RenderMode.slideshow, generate_music=False)

            self.assertNotIn("STABILITY_API_KEY", missing)
            self.assertNotIn("ELEVENLABS_API_KEY", missing)
        finally:
            for key, value in prior.items():
                setattr(settings, key, value)

    def test_pov_requires_elevenlabs_key_even_when_background_music_is_disabled(self) -> None:
        fields = ("stability_api_key", "elevenlabs_api_key", "gmi_api_key")
        prior = {field: getattr(settings, field) for field in fields}
        try:
            settings.stability_api_key = ""
            settings.elevenlabs_api_key = ""
            settings.gmi_api_key = "test-gmi-key"

            missing = settings.missing_campaign_settings(RenderMode.pov, generate_music=False)

            self.assertNotIn("STABILITY_API_KEY", missing)
            self.assertIn("ELEVENLABS_API_KEY", missing)
        finally:
            for key, value in prior.items():
                setattr(settings, key, value)

    def test_cloudflare_provider_saves_raw_image_response(self) -> None:
        class FakeClient:
            def post(self, *args, **kwargs):
                return httpx.Response(
                    200,
                    headers={"content-type": "image/png"},
                    content=b"fake-png-bytes",
                    request=httpx.Request("POST", "https://example.test"),
                )

        with TemporaryDirectory() as temp_dir:
            provider = CloudflareImageProvider(
                account_id="test-account",
                api_token="test-token",
                output_dir=temp_dir,
                http_client=FakeClient(),
            )
            step = Step(
                provider=provider.name,
                model="@cf/bytedance/stable-diffusion-xl-lightning",
                modality=Modality.IMAGE,
                prompt="red circle",
                params={"width": 768, "height": 1344},
            )

            result = provider.generate(step)

            self.assertEqual(len(result.assets), 1)
            self.assertEqual(result.assets[0].media_type, "image/png")
            self.assertTrue(Path(str(result.assets[0].url).removeprefix("file://")).exists())

    def test_prompt_moderation_blocks_unambiguous_high_risk_request(self) -> None:
        with self.assertRaises(ContentSafetyError):
            ensure_prompt_allowed("Create explicit underage sexual content")

    def test_output_moderation_rejects_unsupported_media(self) -> None:
        with self.assertRaises(ContentSafetyError):
            ensure_assets_allowed(
                [Asset(url="https://example.test/output.txt", media_type="text/plain")]
            )

    def test_output_moderation_accepts_standard_render_asset(self) -> None:
        ensure_assets_allowed([Asset(url="https://example.test/reel.mp4", media_type="video/mp4")])

    def test_shared_caption_filter_escapes_unsafe_ffmpeg_characters(self) -> None:
        filter_text = caption_drawtext_filter("Save 20%: it's time")
        self.assertIn(r"20\%\: it\'s", filter_text)
        self.assertIn("y=h*0.80", filter_text)


if __name__ == "__main__":
    unittest.main()
