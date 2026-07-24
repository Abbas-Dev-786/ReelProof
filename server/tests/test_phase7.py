from __future__ import annotations

import unittest

from genblaze_core import Asset

from app.engine.beat_render import _image_provider, _video_provider
from app.engine.safety import ContentSafetyError, ensure_assets_allowed, ensure_prompt_allowed


class ReliabilityAndSafetyTests(unittest.TestCase):
    def test_image_and_video_providers_use_their_expected_retry_policies(self) -> None:
        self.assertEqual(_image_provider().retry_policy.max_attempts, 7)
        self.assertEqual(_video_provider().retry_policy.max_attempts, 2)

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


if __name__ == "__main__":
    unittest.main()
