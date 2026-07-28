from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode

from app.config import settings
from app.engine.assemble import _build_video_filter, assemble_pov_montage, assemble_slideshow
from app.engine.captions import _ffmpeg_escape, _wrap
from app.engine.planner import parse_beat_plan, plan_beats
from app.engine.run_engine import run_campaign
from app.schemas import BeatPlan, JobStatus, RenderMode


class PlannerParsingTests(unittest.TestCase):
    def test_planner_uses_the_configured_text_specialist_and_json_schema(self) -> None:
        prior_provider = settings.llm_provider
        prior_key = settings.nvidia_api_key
        prior_model = settings.nvidia_planner_model
        prior_url = settings.nvidia_chat_base_url
        prior_timeout = settings.nvidia_chat_timeout_sec
        settings.llm_provider = "nvidia"
        settings.nvidia_api_key = "test-nvidia-key"
        settings.nvidia_planner_model = "z-ai/glm-5.2"
        settings.nvidia_chat_base_url = "https://nim.example.test/v1"
        settings.nvidia_chat_timeout_sec = 30.0
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
            settings.llm_provider = prior_provider
            settings.nvidia_api_key = prior_key
            settings.nvidia_planner_model = prior_model
            settings.nvidia_chat_base_url = prior_url
            settings.nvidia_chat_timeout_sec = prior_timeout

        self.assertEqual(plan.hook, "h")
        self.assertEqual(chat.call_args.args[0], "z-ai/glm-5.2")
        self.assertIs(chat.call_args.kwargs["response_format"], BeatPlan)
        self.assertEqual(chat.call_args.kwargs["api_key"], "test-nvidia-key")
        self.assertEqual(chat.call_args.kwargs["base_url"], "https://nim.example.test/v1")
        self.assertEqual(chat.call_args.kwargs["timeout"], 30.0)
        self.assertEqual(chat.call_args.kwargs["max_tokens"], 2048)

    def test_planner_retries_one_transient_nvidia_failure_with_no_sdk_retries(self) -> None:
        prior_provider = settings.llm_provider
        prior_key = settings.nvidia_api_key
        prior_attempts = settings.nvidia_chat_max_attempts
        settings.llm_provider = "nvidia"
        settings.nvidia_api_key = "test-nvidia-key"
        settings.nvidia_chat_max_attempts = 2
        response = SimpleNamespace(
            text=(
                '{"hook":"h","beats":[{"index":0,"concept":"c","caption":"x"}],'
                '"suggested_caption":"s","hashtags":[]}'
            )
        )
        try:
            with (
                patch("app.engine.planner.OpenAI") as openai,
                patch(
                    "app.engine.planner.chat",
                    side_effect=[
                        ProviderError("timeout", error_code=ProviderErrorCode.TIMEOUT),
                        response,
                    ],
                ) as chat,
                patch("app.engine.planner.time.sleep") as sleep,
            ):
                plan = plan_beats("Coffee", beat_count=1)
        finally:
            settings.llm_provider = prior_provider
            settings.nvidia_api_key = prior_key
            settings.nvidia_chat_max_attempts = prior_attempts

        self.assertEqual(plan.hook, "h")
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(openai.call_count, 2)
        self.assertTrue(all(call.kwargs["max_retries"] == 0 for call in openai.call_args_list))
        sleep.assert_called_once_with(1.0)

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

    def test_pov_captions_must_match_clip_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "must match"):
            assemble_pov_montage(
                ["file:///one.mp4"],
                "file:///music.mp3",
                5,
                captions=["first", "second"],
            )

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
        credential_fields = (
            "nvidia_api_key",
            "gmi_api_key",
            "stability_api_key",
            "b2_key_id",
            "b2_app_key",
            "b2_public_url_base",
        )
        prior_values = {field: getattr(settings, field) for field in credential_fields}
        prior_provider = settings.llm_provider
        prior_image_provider = settings.image_provider
        try:
            settings.llm_provider = "nvidia"
            settings.image_provider = "gmi"
            for field in credential_fields:
                setattr(settings, field, "test-value")
            with (
                patch("app.engine.run_engine.build_sink", return_value=SimpleNamespace()),
                patch("app.engine.run_engine.plan_beats", return_value=plan),
                patch("app.engine.run_engine.caption_renderer_error", return_value=None),
                patch(
                    "app.engine.run_engine._run_pov_campaign", return_value=expected
                ) as pov_engine,
            ):
                result = run_campaign(
                    job_id="phase6-test",
                    topic="A quiet coffee ritual",
                    mode=RenderMode.pov,
                    beat_count=3,
                    emit=lambda *_: None,
                )
        finally:
            settings.llm_provider = prior_provider
            settings.image_provider = prior_image_provider
            for field, value in prior_values.items():
                setattr(settings, field, value)

        self.assertIs(result, expected)
        pov_engine.assert_called_once()
        work_dir = pov_engine.call_args.kwargs["work_dir"]
        self.assertTrue(work_dir.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertFalse(work_dir.exists())


if __name__ == "__main__":
    unittest.main()
