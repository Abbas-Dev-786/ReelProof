from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode

from app.config import settings
from app.engine.assemble import _build_video_filter, assemble_pov_montage, assemble_slideshow
from app.engine.beat_render import POVBeatRender
from app.engine.captions import (
    _ffmpeg_escape,
    _wrap,
    caption_drawtext_filter,
    title_drawtext_filter,
)
from app.engine.planner import parse_beat_plan, plan_beats
from app.engine.run_engine import _run_pov_campaign, run_campaign
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

    def test_pov_planner_requires_voiceover_lines(self) -> None:
        prior_key = settings.groq_api_key
        prior_provider = settings.llm_provider
        settings.groq_api_key = "test-groq-key"
        settings.llm_provider = "groq"
        try:
            with patch(
                "app.engine.planner._planner_chat",
                side_effect=[
                    SimpleNamespace(
                        text=(
                            '{"hook":"h","beats":[{"concept":"c","caption":"x","vo":null}],'
                            '"suggested_caption":"s","hashtags":[]}'
                        ),
                        raw={},
                    ),
                    SimpleNamespace(
                        text=(
                            '{"hook":"h","beats":[{"concept":"c","caption":"x","vo":"Say this."}],'
                            '"suggested_caption":"s","hashtags":[]}'
                        ),
                        raw={},
                    ),
                ],
            ) as planner_chat:
                plan = plan_beats("Coffee", beat_count=1, voiceover_required=True)
        finally:
            settings.groq_api_key = prior_key
            settings.llm_provider = prior_provider

        self.assertEqual(plan.beats[0].vo, "Say this.")
        self.assertEqual(planner_chat.call_count, 2)

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
        caption = "This Is A Very Long Caption That Must Stay Visible"
        wrapped = _wrap(caption)
        self.assertGreater(len(wrapped.splitlines()), 1)
        self.assertTrue(all(len(line) <= 16 for line in wrapped.splitlines()))
        self.assertTrue(all(len(line) <= 16 for line in _wrap("W" * 45).splitlines()))
        self.assertEqual(_ffmpeg_escape("it's: ready"), r"it\'s\: ready")

        drawtext = caption_drawtext_filter(caption)
        self.assertIn("\n", drawtext)
        self.assertNotIn(r"\n", drawtext)
        self.assertIn(":y=(h-text_h)*0.82", drawtext)
        self.assertIn(":fix_bounds=1", drawtext)

    def test_title_text_is_centered_without_a_content_caption_box(self) -> None:
        drawtext = title_drawtext_filter("A Quiet Coffee Ritual")
        self.assertIn(":x=(w-text_w)/2", drawtext)
        self.assertIn(":y=(h-text_h)/2", drawtext)
        self.assertNotIn(":box=1", drawtext)

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

    def test_title_card_can_have_a_shorter_duration(self) -> None:
        graph, duration = _build_video_filter(
            n=4,
            beat_duration=3.5,
            transition_duration=0.35,
            title_duration=2.5,
        )
        self.assertIn("xfade=transition=fade", graph)
        self.assertAlmostEqual(duration, 11.95)

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
            "elevenlabs_api_key",
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

    def test_slideshow_can_skip_background_music(self) -> None:
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
        loop_result = SimpleNamespace(
            asset_url="https://example.test/image.png",
            score=0.9,
            iterations=1,
            passed=True,
            total_cost_usd=0.01,
        )
        credential_fields = (
            "groq_api_key",
            "stability_api_key",
            "b2_key_id",
            "b2_app_key",
            "b2_public_url_base",
            "cloudflare_account_id",
            "cloudflare_api_token",
        )
        prior_values = {field: getattr(settings, field) for field in credential_fields}
        prior_provider = settings.llm_provider
        prior_image_provider = settings.image_provider
        events: list[tuple[str, dict]] = []
        try:
            settings.llm_provider = "groq"
            settings.image_provider = "cloudflare"
            for field in credential_fields:
                setattr(settings, field, "test-value")
            settings.stability_api_key = ""
            with (
                patch("app.engine.run_engine.build_sink", return_value=SimpleNamespace()),
                patch("app.engine.run_engine.plan_beats", return_value=plan),
                patch("app.engine.run_engine.caption_renderer_error", return_value=None),
                patch("app.engine.run_engine.run_beat_loop", return_value=loop_result),
                patch(
                    "app.engine.run_engine.render_title_card",
                    return_value="/tmp/title.png",
                ),
                patch("app.engine.run_engine.burn_caption", return_value="/tmp/captioned.png"),
                patch(
                    "app.engine.run_engine._store_local_intermediate",
                    return_value="https://example.test/captioned.png",
                ),
                patch("app.engine.run_engine.generate_music_asset") as generate_music,
                patch("app.engine.run_engine.generate_voiceover_asset") as generate_voiceover,
                patch("app.engine.run_engine.readable_asset_url", side_effect=lambda url: url),
                patch(
                    "app.engine.run_engine.assemble_slideshow",
                    return_value="/tmp/reel.mp4",
                ) as assemble,
                patch(
                    "app.engine.run_engine._store_final_reel",
                    return_value=(
                        "https://example.test/reel.mp4",
                        "a" * 64,
                        "https://example.test/manifest.json",
                        "run-final",
                        True,
                    ),
                ),
            ):
                result = run_campaign(
                    job_id="no-music-test",
                    topic="A quiet coffee ritual",
                    mode=RenderMode.slideshow,
                    beat_count=3,
                    emit=lambda event_type, data: events.append((event_type, data)),
                    generate_music=False,
                )
        finally:
            settings.llm_provider = prior_provider
            settings.image_provider = prior_image_provider
            for field, value in prior_values.items():
                setattr(settings, field, value)

        self.assertEqual(result.status, JobStatus.done)
        self.assertFalse(result.generate_music)
        self.assertIsNone(result.music_url)
        generate_music.assert_not_called()
        generate_voiceover.assert_not_called()
        self.assertIsNone(assemble.call_args.args[1])
        self.assertEqual(
            assemble.call_args.args[0],
            ["/tmp/title.png", "/tmp/captioned.png", "/tmp/captioned.png", "/tmp/captioned.png"],
        )
        self.assertEqual(
            assemble.call_args.kwargs["title_duration"],
            settings.slideshow_title_duration_sec,
        )
        self.assertIn(
            ("step.completed", {"step": "audio", "enabled": False, "skipped": True}), events
        )

    def test_pov_generates_voiceover_even_when_background_music_is_disabled(self) -> None:
        plan = BeatPlan(
            hook="A quiet coffee ritual",
            beats=[
                {"index": 0, "concept": "coffee", "caption": "Brew better", "vo": "Brew better."},
                {"index": 1, "concept": "pour over", "caption": "Slow down", "vo": "Slow down."},
                {
                    "index": 2,
                    "concept": "morning desk",
                    "caption": "Start here",
                    "vo": "Start here.",
                },
            ],
            suggested_caption="Make room for ritual.",
            hashtags=["coffee"],
        )
        rendered = POVBeatRender(
            image_url="https://example.test/image.png",
            video_url="https://example.test/video.mp4",
            cost_usd=0.02,
        )
        voiceover = SimpleNamespace(url="https://example.test/voiceover.mp3", run_id=None)
        events: list[tuple[str, dict]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("app.engine.run_engine.pending_checkpoints", return_value=[]),
                patch("app.engine.run_engine.build_sink", return_value=SimpleNamespace()),
                patch(
                    "app.engine.run_engine._render_or_resume_pov_beat",
                    new=AsyncMock(return_value=rendered),
                ),
                patch("app.engine.run_engine.generate_music_asset") as generate_music,
                patch(
                    "app.engine.run_engine.generate_voiceover_asset",
                    return_value=voiceover,
                ) as generate_voiceover,
                patch("app.engine.run_engine.readable_asset_url", side_effect=lambda url: url),
                patch(
                    "app.engine.run_engine.assemble_pov_montage",
                    return_value="/tmp/reel.mp4",
                ) as assemble,
                patch(
                    "app.engine.run_engine._store_final_reel",
                    return_value=(
                        "https://example.test/reel.mp4",
                        "a" * 64,
                        "https://example.test/manifest.json",
                        "run-final",
                        True,
                    ),
                ),
            ):
                result = _run_pov_campaign(
                    job_id="pov-no-music-test",
                    topic="A quiet coffee ritual",
                    beat_plan=plan,
                    emit=lambda event_type, data: events.append((event_type, data)),
                    sink=SimpleNamespace(),
                    work_dir=Path(temp_dir),
                    product_assets=None,
                    record_provenance=None,
                    generate_music=False,
                )

        self.assertEqual(result.status, JobStatus.done)
        self.assertFalse(result.generate_music)
        self.assertIsNone(result.music_url)
        generate_music.assert_not_called()
        generate_voiceover.assert_called_once()
        self.assertTrue(generate_voiceover.call_args.kwargs["force"])
        self.assertIsNone(assemble.call_args.args[1])
        self.assertEqual(
            assemble.call_args.kwargs["voiceover_url"], "https://example.test/voiceover.mp3"
        )
        self.assertIn(
            ("step.completed", {"step": "audio", "enabled": False, "skipped": True}), events
        )
        self.assertIn(("step.completed", {"step": "voiceover", "enabled": True}), events)


if __name__ == "__main__":
    unittest.main()
