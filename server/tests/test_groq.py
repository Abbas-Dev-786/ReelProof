from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.config import settings
from app.engine.groq import chat
from app.engine.judge import VisionJudge
from app.engine.planner import plan_beats
from app.schemas import BeatPlan


class GroqChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prior_tracing = settings.langsmith_tracing
        settings.langsmith_tracing = False

    def tearDown(self) -> None:
        settings.langsmith_tracing = self.prior_tracing

    def test_strict_planner_schema_requires_nullable_optional_fields(self) -> None:
        raw = SimpleNamespace(
            model_dump=lambda: {
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            }
        )
        client = MagicMock()
        client.chat.completions.create.return_value = raw
        with patch("app.engine.groq.OpenAI", return_value=client) as openai:
            response = chat(
                "openai/gpt-oss-20b",
                prompt="Plan five beats",
                response_format=BeatPlan,
                api_key="test-groq-key",
                max_tokens=2048,
                max_attempts=1,
            )

        payload = client.chat.completions.create.call_args.kwargs
        schema = payload["response_format"]["json_schema"]
        beat_schema = schema["schema"]["$defs"]["Beat"]
        self.assertTrue(schema["strict"])
        self.assertEqual(set(beat_schema["required"]), {"index", "concept", "caption", "vo"})
        self.assertFalse(beat_schema["additionalProperties"])
        self.assertEqual(payload["max_completion_tokens"], 2048)
        self.assertEqual(response.raw["_reelproof_provider"], "groq")
        self.assertEqual(response.raw["_reelproof_attempts"], 1)
        openai.assert_called_once()
        self.assertEqual(openai.call_args.kwargs["max_retries"], 0)

    def test_retries_rate_limit_once_without_sdk_retries(self) -> None:
        rate_limited = SimpleNamespace(
            response=SimpleNamespace(status_code=429, headers={"Retry-After": "2"})
        )
        first_client = MagicMock()
        first_client.chat.completions.create.side_effect = Exception("rate limit")
        first_client.chat.completions.create.side_effect.response = rate_limited.response
        second_client = MagicMock()
        second_client.chat.completions.create.return_value = SimpleNamespace(
            model_dump=lambda: {
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {},
            }
        )
        with (
            patch("app.engine.groq.OpenAI", side_effect=[first_client, second_client]) as openai,
            patch("app.engine.groq.time.sleep") as sleep,
        ):
            response = chat(
                "openai/gpt-oss-20b",
                prompt="Retry me",
                api_key="test-groq-key",
                max_attempts=2,
                retry_backoff_sec=1,
                max_retry_delay_sec=5,
            )

        self.assertEqual(response.raw["_reelproof_attempts"], 2)
        self.assertEqual(openai.call_count, 2)
        self.assertTrue(all(call.kwargs["max_retries"] == 0 for call in openai.call_args_list))
        sleep.assert_called_once_with(2.0)


class GroqProviderDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prior_values = {
            name: getattr(settings, name)
            for name in (
                "llm_provider",
                "groq_api_key",
                "groq_planner_model",
                "groq_vision_model",
                "langsmith_tracing",
            )
        }
        settings.llm_provider = "groq"
        settings.groq_api_key = "test-groq-key"
        settings.langsmith_tracing = False

    def tearDown(self) -> None:
        for name, value in self.prior_values.items():
            setattr(settings, name, value)

    def test_planner_uses_groq_strict_schema_model(self) -> None:
        response = SimpleNamespace(
            text=(
                '{"hook":"h","beats":[{"index":0,"concept":"c","caption":"x"}],'
                '"suggested_caption":"s","hashtags":[]}'
            ),
            model="openai/gpt-oss-20b",
            raw={"_reelproof_attempts": 1},
            tokens_in=10,
            tokens_out=5,
        )
        with patch("app.engine.planner.groq_chat", return_value=response) as groq_chat:
            plan = plan_beats("Coffee", beat_count=1)

        self.assertEqual(plan.hook, "h")
        self.assertEqual(groq_chat.call_args.args[0], settings.groq_planner_model)
        self.assertIs(groq_chat.call_args.kwargs["response_format"], BeatPlan)
        self.assertTrue(groq_chat.call_args.kwargs["strict_json_schema"])
        self.assertEqual(groq_chat.call_args.kwargs["api_key"], "test-groq-key")

    def test_judge_uses_groq_vision_model_with_json_object_mode(self) -> None:
        response = SimpleNamespace(
            text=(
                '{"hook_strength":0.8,"text_legibility":0.9,"visual_artifacts":0.7,'
                '"on_brand":0.85,"overall":0.81,"feedback":null}'
            ),
            model="qwen/qwen3.6-27b",
            raw={"_reelproof_attempts": 1},
            tokens_in=30,
            tokens_out=20,
        )
        result = SimpleNamespace(
            run=SimpleNamespace(
                steps=[SimpleNamespace(assets=[SimpleNamespace(url="https://example.test/frame.png")])]
            )
        )
        with patch("app.engine.judge.groq_chat", return_value=response) as groq_chat:
            evaluation = VisionJudge().evaluate(result)

        self.assertTrue(evaluation.passed)
        self.assertEqual(groq_chat.call_args.args[0], settings.groq_vision_model)
        self.assertFalse(groq_chat.call_args.kwargs["strict_json_schema"])
        self.assertEqual(
            groq_chat.call_args.kwargs["response_format"], {"type": "json_object"}
        )
        self.assertEqual(groq_chat.call_args.kwargs["api_key"], "test-groq-key")


if __name__ == "__main__":
    unittest.main()
