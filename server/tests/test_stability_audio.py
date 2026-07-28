from __future__ import annotations

import tempfile
import unittest

import httpx
from genblaze_core import Modality, Step

from app.engine.audio import _music_output_dir
from app.engine.stability_audio import StabilityAudioProvider, _MultipartFormDataClient
from app.workspace import media_workspace


class StabilityAudioMultipartTests(unittest.TestCase):
    def test_music_output_dir_uses_active_media_workspace(self) -> None:
        with media_workspace() as workspace:
            output_dir = _music_output_dir()

        self.assertTrue(output_dir.is_relative_to(workspace))
        self.assertEqual(output_dir.name, "music")
        self.assertFalse(workspace.exists())

    def test_text_to_audio_request_uses_multipart_form_data(self) -> None:
        captured: dict[str, bytes | str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["content_type"] = request.headers["content-type"]
            captured["authorization"] = request.headers["authorization"]
            captured["accept"] = request.headers["accept"]
            captured["body"] = request.read()
            return httpx.Response(200, content=b"not-a-real-mp3", request=request)

        with tempfile.TemporaryDirectory() as output_dir:
            provider = StabilityAudioProvider(api_key="test-key", output_dir=output_dir)
            provider._http_client = _MultipartFormDataClient(
                httpx.Client(transport=httpx.MockTransport(handler))
            )
            try:
                step = Step(
                    provider="stability-audio",
                    model="stable-audio-2.5",
                    modality=Modality.AUDIO,
                    prompt="Upbeat instrumental music",
                    seed=7,
                    params={"duration": 20, "output_format": "mp3"},
                )
                result = provider.generate(step)
            finally:
                provider.close()

        self.assertEqual(captured["authorization"], "Bearer test-key")
        self.assertEqual(captured["accept"], "audio/*")
        self.assertTrue(str(captured["content_type"]).startswith("multipart/form-data; boundary="))
        body = bytes(captured["body"])
        self.assertIn(b'name="prompt"\r\n\r\nUpbeat instrumental music\r\n', body)
        self.assertIn(b'name="output_format"\r\n\r\nmp3\r\n', body)
        self.assertIn(b'name="duration"\r\n\r\n20.0\r\n', body)
        self.assertIn(b'name="seed"\r\n\r\n7\r\n', body)
        self.assertEqual(len(result.assets), 1)


if __name__ == "__main__":
    unittest.main()
