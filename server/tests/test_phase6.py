from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from genblaze_core import Asset

from app.engine.beat_render import resume_pov_video
from app.jobs import store


class POVCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = store.DB_PATH
        store.DB_PATH = Path(self.temp_dir.name) / "jobs.db"
        store.init_db()

    def tearDown(self) -> None:
        store.DB_PATH = self.previous_db_path
        self.temp_dir.cleanup()

    def test_checkpoint_round_trip_and_completion(self) -> None:
        payload = {
            "kind": "pov-video",
            "beat_index": 1,
            "model": "pixverse-v5.6-i2v",
            "prompt": "Animate a coffee pour",
            "duration": 5,
            "aspect_ratio": "9:16",
            "source_asset": Asset(
                url="https://example.test/frame.png", media_type="image/png"
            ).model_dump(mode="json"),
        }
        store.save_checkpoint("job-1", "step-1", "prediction-1", payload)

        checkpoints = store.pending_checkpoints("job-1")
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0]["prediction_id"], "prediction-1")
        self.assertEqual(checkpoints[0]["checkpoint"]["beat_index"], 1)

        store.complete_checkpoint("job-1", "step-1")
        self.assertEqual(store.pending_checkpoints("job-1"), [])

    def test_resume_polls_existing_prediction_without_resubmitting(self) -> None:
        checkpoint = {
            "job_id": "job-1",
            "step_id": "step-1",
            "prediction_id": "prediction-1",
            "checkpoint": {
                "kind": "pov-video",
                "beat_index": 0,
                "model": "pixverse-v5.6-i2v",
                "prompt": "Animate a coffee pour",
                "duration": 5,
                "aspect_ratio": "9:16",
                "source_asset": Asset(
                    url="https://example.test/frame.png", media_type="image/png"
                ).model_dump(mode="json"),
            },
        }
        provider = SimpleNamespace()

        async def aresume(prediction_id: str, step: object) -> object:
            self.assertEqual(prediction_id, "prediction-1")
            self.assertEqual(step.step_id, "step-1")  # type: ignore[attr-defined]
            self.assertEqual(  # type: ignore[attr-defined]
                step.inputs[0].url, "https://example.test/frame.png"
            )
            return SimpleNamespace(
                assets=[Asset(url="https://example.test/clip.mp4", media_type="video/mp4")],
                cost_usd=0.03,
            )

        provider.aresume = aresume
        provider.name = "gmicloud"
        with patch("app.engine.beat_render._video_provider", return_value=provider):
            result = asyncio.run(resume_pov_video(checkpoint))

        self.assertEqual(result.image_url, "https://example.test/frame.png")
        self.assertEqual(result.video_url, "https://example.test/clip.mp4")
        self.assertEqual(result.cost_usd, 0.03)


if __name__ == "__main__":
    unittest.main()
