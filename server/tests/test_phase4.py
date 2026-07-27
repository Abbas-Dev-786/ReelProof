from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from genblaze_core import EvaluationResult

from app.config import settings
from app.engine.judge import JudgeScoresResponse, VisionJudge, parse_judge_scores
from app.engine.loop import refine_prompt, run_beat_loop
from app.schemas import Beat
from app.storage import readable_asset_url


class JudgeResponseTests(unittest.TestCase):
    def test_judge_uses_the_configured_vision_specialist_and_json_schema(self) -> None:
        prior_provider = settings.llm_provider
        prior_key = settings.nvidia_api_key
        prior_model = settings.nvidia_vision_model
        prior_url = settings.nvidia_chat_base_url
        settings.llm_provider = "nvidia"
        settings.nvidia_api_key = "test-nvidia-key"
        settings.nvidia_vision_model = "qwen/qwen3.5-397b-a17b"
        settings.nvidia_chat_base_url = "https://nim.example.test/v1"
        result = SimpleNamespace(
            run=SimpleNamespace(
                steps=[SimpleNamespace(assets=[SimpleNamespace(url="https://example.test/frame.png")])]
            )
        )
        response = SimpleNamespace(
            text=(
                '{"hook_strength":0.8,"text_legibility":0.9,"visual_artifacts":0.7,'
                '"on_brand":0.85,"overall":0.81,"feedback":null}'
            )
        )
        try:
            with (
                patch("app.engine.judge.chat", return_value=response) as chat,
                patch(
                    "app.engine.judge.readable_asset_url",
                    return_value="https://s3.example.test/frame.png?redacted=signature",
                ) as signed_url,
            ):
                evaluation = VisionJudge().evaluate(result)
        finally:
            settings.llm_provider = prior_provider
            settings.nvidia_api_key = prior_key
            settings.nvidia_vision_model = prior_model
            settings.nvidia_chat_base_url = prior_url

        self.assertTrue(evaluation.passed)
        self.assertEqual(chat.call_args.args[0], "qwen/qwen3.5-397b-a17b")
        self.assertIs(chat.call_args.kwargs["response_format"], JudgeScoresResponse)
        self.assertEqual(chat.call_args.kwargs["temperature"], 0.1)
        self.assertEqual(chat.call_args.kwargs["api_key"], "test-nvidia-key")
        self.assertEqual(chat.call_args.kwargs["base_url"], "https://nim.example.test/v1")
        signed_url.assert_called_once_with("https://example.test/frame.png")
        self.assertEqual(
            chat.call_args.kwargs["messages"][0]["content"][1]["image_url"]["url"],
            "https://s3.example.test/frame.png?redacted=signature",
        )

    def test_parses_fenced_scores(self) -> None:
        scores = parse_judge_scores(
            """```json
            {"hook_strength": 0.8, "text_legibility": 0.9, "visual_artifacts": 0.7,
             "on_brand": 0.85, "overall": 0.81, "feedback": null}
            ```"""
        )
        self.assertEqual(scores["overall"], 0.81)
        self.assertIsNone(scores["feedback"])

    def test_rejects_out_of_range_scores(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            parse_judge_scores(
                '{"hook_strength": 1.2, "text_legibility": 0.9, "visual_artifacts": 0.7,'
                '"on_brand": 0.85, "overall": 0.81, "feedback": null}'
            )


class VisionAssetUrlTests(unittest.TestCase):
    def test_signs_b2_asset_urls_for_external_vision_models(self) -> None:
        backend = MagicMock()
        backend.key_from_url.return_value = "reelproof/run/frame.png"
        backend.presigned_get_url.return_value = "https://s3.example.test/frame.png?signature=secret"

        with patch("app.storage.get_backend", return_value=backend):
            url = readable_asset_url("https://cdn.example.test/reelproof/run/frame.png")

        self.assertEqual(url, "https://s3.example.test/frame.png?signature=secret")
        backend.presigned_get_url.assert_called_once_with("reelproof/run/frame.png", expires_in=900)

    def test_keeps_foreign_asset_urls_unchanged(self) -> None:
        backend = MagicMock()
        backend.key_from_url.return_value = None

        with patch("app.storage.get_backend", return_value=backend):
            url = readable_asset_url("https://provider.example.test/frame.png")

        self.assertEqual(url, "https://provider.example.test/frame.png")
        backend.presigned_get_url.assert_not_called()


class SelfHealingLoopTests(unittest.TestCase):
    def test_refinement_appends_previous_feedback(self) -> None:
        self.assertEqual(
            refine_prompt(
                "A bright coffee setup", "leave a clean lower third", "warm editorial lighting"
            ),
            "A bright coffee setup — warm editorial lighting — leave a clean lower third",
        )

    def test_loop_reports_every_attempt_and_returns_last_result(self) -> None:
        first_result = SimpleNamespace(
            run=SimpleNamespace(
                run_id="run-1",
                parent_run_id=None,
                steps=[
                    SimpleNamespace(assets=[SimpleNamespace(url="https://example.test/first.png")])
                ],
            ),
            manifest=SimpleNamespace(
                canonical_hash="hash-1", manifest_uri="uri-1", model_dump_json=lambda: "manifest-1"
            ),
        )
        second_result = SimpleNamespace(
            run=SimpleNamespace(
                run_id="run-2",
                parent_run_id="run-1",
                steps=[
                    SimpleNamespace(assets=[SimpleNamespace(url="https://example.test/final.png")])
                ],
            ),
            manifest=SimpleNamespace(
                canonical_hash="hash-2", manifest_uri="uri-2", model_dump_json=lambda: "manifest-2"
            ),
        )
        agent_result = SimpleNamespace(
            iterations=[
                SimpleNamespace(
                    index=0,
                    result=first_result,
                    evaluation=EvaluationResult(False, 0.4, "clean lower third"),
                ),
                SimpleNamespace(
                    index=1, result=second_result, evaluation=EvaluationResult(True, 0.9, None)
                ),
            ],
            passed=True,
            total_cost_usd=0.014,
        )

        class FakeAgentLoop:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def run(self, **_kwargs):
                return agent_result

        records: list[dict] = []
        prior_key = settings.gmi_api_key
        settings.gmi_api_key = "test-key"
        try:
            with patch("app.engine.loop.AgentLoop", FakeAgentLoop):
                result = run_beat_loop(
                    Beat(index=0, concept="coffee", caption="Brew Better"),
                    sink=SimpleNamespace(),
                    on_iteration=records.append,
                )
        finally:
            settings.gmi_api_key = prior_key

        self.assertEqual(result.asset_url, "https://example.test/final.png")
        self.assertEqual(result.iterations, 2)
        self.assertTrue(result.passed)
        self.assertEqual(result.total_cost_usd, 0.014)
        self.assertEqual([record["run_id"] for record in records], ["run-1", "run-2"])
        self.assertEqual(records[1]["parent_run_id"], "run-1")


if __name__ == "__main__":
    unittest.main()
