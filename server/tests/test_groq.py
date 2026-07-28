from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode

from app.config import settings
from app.engine.groq import DEFAULT_CHAT_BASE_URL, _groq_rate_limiter, chat
from app.engine.judge import VisionJudge
from app.engine.planner import _GROQ_BEAT_PLAN_RESPONSE_FORMAT, plan_beats


class GroqChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prior_tracing = settings.langsmith_tracing
        settings.langsmith_tracing = False

    def tearDown(self) -> None:
        settings.langsmith_tracing = self.prior_tracing
        _groq_rate_limiter.reset()

    def test_token_pacer_spaces_repeated_model_calls(self) -> None:
        _groq_rate_limiter.reset()

        with patch("app.engine.groq.time.monotonic", side_effect=[100.0, 105.0]):
            first_delay = _groq_rate_limiter.reserve(
                "vision:qwen",
                estimated_tokens=2500,
                tokens_per_minute=8000,
                safety_factor=0.9,
            )
            second_delay = _groq_rate_limiter.reserve(
                "vision:qwen",
                estimated_tokens=2500,
                tokens_per_minute=8000,
                safety_factor=0.9,
            )

        self.assertEqual(first_delay, 0.0)
        self.assertAlmostEqual(second_delay, 15.8333333333)

    def test_token_pacer_honors_shared_provider_cooldown(self) -> None:
        _groq_rate_limiter.reset()

        with patch("app.engine.groq.time.monotonic", side_effect=[100.0, 101.0]):
            _groq_rate_limiter.cooldown("vision:qwen", 3.0)
            delay = _groq_rate_limiter.reserve(
                "vision:qwen",
                estimated_tokens=1,
                tokens_per_minute=60,
                safety_factor=1.0,
            )

        self.assertEqual(delay, 2.0)

    def test_strict_planner_request_includes_a_bounded_reasoning_budget(self) -> None:
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
                api_key="test-groq-key",
                max_tokens=2048,
                reasoning_effort="low",
                response_format=_GROQ_BEAT_PLAN_RESPONSE_FORMAT,
                strict_json_schema=True,
                max_attempts=1,
            )

        payload = client.chat.completions.create.call_args.kwargs
        response_format = payload["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        schema = response_format["json_schema"]["schema"]
        self.assertNotIn("$defs", schema)
        self.assertFalse(schema["additionalProperties"])
        beat_schema = schema["properties"]["beats"]["items"]
        self.assertEqual(beat_schema["required"], ["concept", "caption", "vo"])
        self.assertFalse(beat_schema["additionalProperties"])
        self.assertEqual(beat_schema["properties"]["vo"]["type"], ["string", "null"])
        self.assertEqual(payload["max_completion_tokens"], 2048)
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(response.raw["_reelproof_provider"], "groq")
        self.assertEqual(response.raw["_reelproof_attempts"], 1)
        openai.assert_called_once()
        self.assertEqual(openai.call_args.kwargs["max_retries"], 0)

    def test_retries_groq_json_validation_failures(self) -> None:
        validation_error = Exception("Error code: 400 - {'code': 'json_validate_failed'}")
        validation_error.response = SimpleNamespace(status_code=400, headers={})
        first_client = MagicMock()
        first_client.chat.completions.create.side_effect = validation_error
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
                prompt="Retry JSON output",
                api_key="test-groq-key",
                max_attempts=2,
            )

        self.assertEqual(response.raw["_reelproof_attempts"], 2)
        self.assertEqual(openai.call_count, 2)
        sleep.assert_called_once_with(1.0)

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
        sleep.assert_called_once_with(2.5)

    def test_retries_rate_limit_using_groq_body_cooldown(self) -> None:
        first_client = MagicMock()
        rate_limit_error = Exception(
            "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
            "qwen/qwen3.6-27b on tokens per minute. Please try again in 1.74s.', "
            "'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
        )
        rate_limit_error.response = SimpleNamespace(status_code=429, headers={})
        first_client.chat.completions.create.side_effect = rate_limit_error
        second_client = MagicMock()
        second_client.chat.completions.create.return_value = SimpleNamespace(
            model_dump=lambda: {
                "model": "qwen/qwen3.6-27b",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {},
            }
        )

        with (
            patch("app.engine.groq.OpenAI", side_effect=[first_client, second_client]) as openai,
            patch("app.engine.groq.time.sleep") as sleep,
        ):
            response = chat(
                "qwen/qwen3.6-27b",
                prompt="Retry me",
                api_key="test-groq-key",
                max_attempts=2,
                retry_backoff_sec=1,
                max_retry_delay_sec=5,
            )

        self.assertEqual(response.raw["_reelproof_attempts"], 2)
        self.assertEqual(openai.call_count, 2)
        sleep.assert_called_once_with(2.24)

    def test_accepts_a_full_chat_completions_endpoint_as_the_base_url(self) -> None:
        client = MagicMock()
        client.chat.completions.create.return_value = SimpleNamespace(
            model_dump=lambda: {
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {},
            }
        )
        with patch("app.engine.groq.OpenAI", return_value=client) as openai:
            chat(
                "openai/gpt-oss-20b",
                prompt="Use the configured endpoint",
                api_key="test-groq-key",
                base_url=f"{DEFAULT_CHAT_BASE_URL}/chat/completions",
                max_attempts=1,
            )

        self.assertEqual(openai.call_args.kwargs["base_url"], DEFAULT_CHAT_BASE_URL)

    def test_redacts_signed_asset_urls_from_trace_inputs(self) -> None:
        raw = SimpleNamespace(
            model_dump=lambda: {
                "model": "qwen/qwen3.6-27b",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {},
            }
        )
        client = MagicMock()
        client.chat.completions.create.return_value = raw
        trace_inputs: dict[str, object] = {}

        @contextmanager
        def record_trace(*_args, **kwargs):
            trace_inputs.update(kwargs["inputs"])
            yield None

        signed_url = (
            "https://s3.example.test/reelproof/frame.png?"
            "X-Amz-Credential=access-key&X-Amz-Signature=secret-signature"
        )
        with (
            patch("app.engine.groq.OpenAI", return_value=client),
            patch("app.engine.groq.trace_operation", record_trace),
        ):
            chat(
                "qwen/qwen3.6-27b",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Score this image"},
                            {"type": "image_url", "image_url": {"url": signed_url}},
                        ],
                    }
                ],
                api_key="test-groq-key",
                max_attempts=1,
            )

        traced_url = trace_inputs["messages"][0]["content"][1]["image_url"]["url"]
        self.assertEqual(traced_url, "https://s3.example.test/reelproof/frame.png?redacted=1")


class GroqProviderDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prior_values = {
            name: getattr(settings, name)
            for name in (
                "llm_provider",
                "groq_api_key",
                "groq_planner_model",
                "groq_planner_fallback_model",
                "groq_planner_max_tokens",
                "groq_vision_model",
                "groq_vision_max_tokens",
                "groq_vision_rate_limit_tpm",
                "groq_vision_rate_limit_estimated_tokens",
                "groq_vision_rate_limit_safety_factor",
                "langsmith_tracing",
            )
        }
        settings.llm_provider = "groq"
        settings.groq_api_key = "test-groq-key"
        settings.groq_planner_max_tokens = 2048
        settings.groq_planner_fallback_model = "openai/gpt-oss-120b"
        settings.groq_vision_max_tokens = 256
        settings.groq_vision_rate_limit_tpm = 8000
        settings.groq_vision_rate_limit_estimated_tokens = 2500
        settings.groq_vision_rate_limit_safety_factor = 0.9
        settings.langsmith_tracing = False

    def tearDown(self) -> None:
        for name, value in self.prior_values.items():
            setattr(settings, name, value)

    def test_planner_uses_strict_json_schema_and_records_the_model(self) -> None:
        response = SimpleNamespace(
            text=(
                '{"hook":"h","beats":[{"concept":"c","caption":"x","vo":null}],'
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
        self.assertEqual([beat.index for beat in plan.beats], [0])
        self.assertEqual(groq_chat.call_args.args[0], settings.groq_planner_model)
        response_format = groq_chat.call_args.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertTrue(groq_chat.call_args.kwargs["strict_json_schema"])
        self.assertEqual(groq_chat.call_args.kwargs["api_key"], "test-groq-key")
        self.assertEqual(groq_chat.call_args.kwargs["reasoning_effort"], "low")
        self.assertEqual(groq_chat.call_args.kwargs["max_tokens"], 4096)

    def test_planner_retries_a_response_that_fails_local_schema_validation(self) -> None:
        invalid = SimpleNamespace(
            text=(
                '{"hook":"h","beats":[{"index":0,"concept":"c","caption":"x","vo":null}],'
                '"suggested_caption":"s","hashtags":[]}'
            ),
            raw={},
        )
        valid = SimpleNamespace(
            text=(
                '{"hook":"h","beats":[{"concept":"c","caption":"x","vo":null}],'
                '"suggested_caption":"s","hashtags":[]}'
            ),
            raw={"_reelproof_attempts": 1},
            model="openai/gpt-oss-20b",
            tokens_in=10,
            tokens_out=5,
        )
        with patch("app.engine.planner.groq_chat", side_effect=[invalid, valid]) as groq_chat:
            plan = plan_beats("Coffee", beat_count=1)

        self.assertEqual(plan.hook, "h")
        self.assertEqual(groq_chat.call_count, 2)

    def test_planner_fails_over_only_to_the_equivalent_strict_model(self) -> None:
        primary_failure = ProviderError(
            "Groq primary is temporarily unavailable",
            error_code=ProviderErrorCode.SERVER_ERROR,
        )
        fallback_response = SimpleNamespace(
            text=(
                '{"hook":"h","beats":[{"concept":"c","caption":"x","vo":null}],'
                '"suggested_caption":"s","hashtags":[]}'
            ),
            model=settings.groq_planner_fallback_model,
            raw={"_reelproof_attempts": 1},
            tokens_in=10,
            tokens_out=5,
        )

        with patch(
            "app.engine.planner.groq_chat", side_effect=[primary_failure, fallback_response]
        ) as groq_chat:
            plan = plan_beats("Coffee", beat_count=1)

        self.assertEqual(plan.hook, "h")
        self.assertEqual(
            [call.args[0] for call in groq_chat.call_args_list],
            [settings.groq_planner_model, settings.groq_planner_fallback_model],
        )
        self.assertTrue(all(call.kwargs["strict_json_schema"] for call in groq_chat.call_args_list))
        self.assertEqual(
            fallback_response.raw["_reelproof_planner_models_tried"],
            [settings.groq_planner_model, settings.groq_planner_fallback_model],
        )

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
                steps=[
                    SimpleNamespace(assets=[SimpleNamespace(url="https://example.test/frame.png")])
                ]
            )
        )
        with (
            patch("app.engine.judge.groq_chat", return_value=response) as groq_chat,
            patch(
                "app.engine.judge.readable_asset_url",
                return_value="https://s3.example.test/frame.png?redacted=signature",
            ),
        ):
            evaluation = VisionJudge().evaluate(result)

        self.assertTrue(evaluation.passed)
        self.assertEqual(groq_chat.call_args.args[0], settings.groq_vision_model)
        self.assertEqual(groq_chat.call_args.kwargs["response_format"], {"type": "json_object"})
        self.assertFalse(groq_chat.call_args.kwargs["strict_json_schema"])
        self.assertEqual(groq_chat.call_args.kwargs["reasoning_effort"], "none")
        self.assertEqual(groq_chat.call_args.kwargs["max_tokens"], 256)
        self.assertEqual(groq_chat.call_args.kwargs["rate_limit_key"], "vision:qwen/qwen3.6-27b")
        self.assertEqual(groq_chat.call_args.kwargs["rate_limit_tpm"], 8000)
        self.assertEqual(groq_chat.call_args.kwargs["rate_limit_estimated_tokens"], 2500)
        self.assertEqual(groq_chat.call_args.kwargs["rate_limit_safety_factor"], 0.9)
        self.assertEqual(groq_chat.call_args.kwargs["api_key"], "test-groq-key")


if __name__ == "__main__":
    unittest.main()
