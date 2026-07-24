from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import settings
from app.engine.assemble import _build_video_filter, assemble_slideshow
from app.engine.captions import _ffmpeg_escape, _wrap
from app.engine.planner import parse_beat_plan, plan_beats
from app.engine.run_engine import run_campaign
from app.schemas import BeatPlan, JobStatus, RenderMode


class PlannerParsingTests(unittest.TestCase):
    def test_planner_uses_the_configured_text_specialist_and_json_schema(self) -> None:
        prior_key = settings.nvidia_api_key
        prior_model = settings.nvidia_planner_model
        prior_url = settings.nvidia_chat_base_url
        settings.nvidia_api_key = "test-nvidia-key"
        settings.nvidia_planner_model = "z-ai/glm-5.2"
        settings.nvidia_chat_base_url = "https://nim.example.test/v1"
        try:
            with patch(
                "app.engine.planner.chat",
                return_value=SimpleNamespace(
                    text=(
                        '{"hook":"h","beats":[{"index":0,"concept":"c","caption":"x"}],'
                        '"suggested_caption":"s","hashtags":[]}'
                    )
                ),
            ) as chat:
                plan = plan_beats("Coffee", beat_count=1)
        finally:
            settings.nvidia_api_key = prior_key
            settings.nvidia_planner_model = prior_model
            settings.nvidia_chat_base_url = prior_url

        self.assertEqual(plan.hook, "h")
        self.assertEqual(chat.call_args.args[0], "z-ai/glm-5.2")
        self.assertIs(chat.call_args.kwargs["response_format"], BeatPlan)
        self.assertEqual(chat.call_args.kwargs["api_key"], "test-nvidia-key")
        self.assertEqual(chat.call_args.kwargs["base_url"], "https://nim.example.test/v1")

    def test_accepts_fenced_json_with_ordered_beats(self) -> None:
        plan = parse_beat_plan(
            """```json
            {
              "hook": "A better morning routine",
              "beats": [
                {"index": 0, "concept": "sunrise desk", "caption": "Start Small", "vo": null},
                {"index": 1, "concept": "coffee beside notebook", "caption": "Stay Consistent", "vo": null}
              ],
              "suggested_caption": "Make tomorrow easier.",
              "hashtags": ["habits", "routine"]
            }
            ```""",
            beat_count=2,
        )

        self.assertEqual(plan.hook, "A better morning routine")
        self.assertEqual([beat.index for beat in plan.beats], [0, 1])

    def test_rejects_wrong_beat_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected exactly 2"):
            parse_beat_plan(
                '{"hook":"h","beats":[{"index":0,"concept":"c","caption":"x"}],'
                '"suggested_caption":"s","hashtags":[]}',
                beat_count=2,
            )

    def test_rejects_non_sequential_indexes(self) -> None:
        with self.assertRaisesRegex(ValueError, "indexes"):
            parse_beat_plan(
                '{"hook":"h","beats":[{"index":1,"concept":"c","caption":"x"}],'
                '"suggested_caption":"s","hashtags":[]}',
                beat_count=1,
            )


class LocalRenderGuardTests(unittest.TestCase):
    def test_caption_text_is_wrapped_and_escaped_for_drawtext(self) -> None:
        wrapped = _wrap("A caption that is deliberately long enough to wrap cleanly", width=16)
        self.assertIn("\n", wrapped)
        self.assertEqual(_ffmpeg_escape("it's: ready"), r"it\'s\: ready")

    def test_assemble_requires_at_least_one_image(self) -> None:
        with self.assertRaisesRegex(ValueError, "without captioned images"):
            assemble_slideshow([], "file:///missing.mp3", 3.5)

    def test_assemble_fails_before_ffmpeg_when_a_frame_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_frame = Path(temp_dir) / "missing.png"
            with self.assertRaisesRegex(FileNotFoundError, "Captioned image files not found"):
                assemble_slideshow(
                    [str(missing_frame)], "file:///missing.mp3", 3.5, output_dir=temp_dir
                )

    def test_crossfade_filter_has_expected_duration(self) -> None:
        graph, duration = _build_video_filter(n=3, beat_duration=3.5, transition_duration=0.35)
        self.assertIn("xfade=transition=fade", graph)
        self.assertAlmostEqual(duration, 9.8)

    def test_pov_requests_dispatch_to_the_phase_six_engine(self) -> None:
        plan = BeatPlan(
            hook="A quiet coffee ritual",
            beats=[
                {"index": 0, "concept": "coffee", "caption": "Brew better"},
                {"index": 1, "concept": "pour over", "caption": "Slow down"},
                {"index": 2, "concept": "morning desk", "caption": "Start here"},
            ],
            suggested_caption="Make room for ritual.",
            hashtags=["coffee"],
        )
        expected = SimpleNamespace(status=JobStatus.done)
        with (
            patch("app.engine.run_engine.build_sink", return_value=SimpleNamespace()),
            patch("app.engine.run_engine.plan_beats", return_value=plan),
            patch("app.engine.run_engine._run_pov_campaign", return_value=expected) as pov_engine,
        ):
            result = run_campaign(
                job_id="phase6-test",
                topic="A quiet coffee ritual",
                mode=RenderMode.pov,
                beat_count=3,
                emit=lambda *_: None,
            )

        self.assertIs(result, expected)
        pov_engine.assert_called_once()


if __name__ == "__main__":
    unittest.main()
