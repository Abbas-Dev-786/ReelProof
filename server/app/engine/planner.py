from __future__ import annotations

import json
import time
from typing import Any

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_nvidia import chat
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError

from ..config import settings
from ..observability import finish_trace, trace_operation
from ..schemas import Beat, BeatPlan
from .groq import chat as groq_chat
from .safety import ensure_prompt_allowed

_SYSTEM = """\
You are a faceless short-form content strategist. Given a topic, produce a beat plan for a
9:16 vertical social video (TikTok/Reels style). Return exactly one JSON object matching the
supplied response schema. Do not include Markdown, code fences, reasoning, or any text before
or after the JSON.

Rules:
- concept must describe a clean, photorealistic, faceless scene (no people's faces)
- caption must be legible on a dark background; use title case; max 8 words
- 3-8 beats depending on beat_count param
- return beats in their intended playback order
- hashtags: 5-10 relevant tags without the # symbol
- every beat must include `vo`; use null when no voiceover line is appropriate
"""

_DEFAULT_NVIDIA_CHAT_BASE_URL = "https://integrate.api.nvidia.com/v1"
_MIN_GROQ_PLANNER_COMPLETION_TOKENS = 4096
_GROQ_PLANNER_LOCAL_VALIDATION_ATTEMPTS = 2
_GROQ_PLANNER_RETRYABLE_ERRORS = frozenset(
    {
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.RATE_LIMIT,
        ProviderErrorCode.SERVER_ERROR,
    }
)
_RETRYABLE_NVIDIA_ERRORS = frozenset(
    {
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.RATE_LIMIT,
        ProviderErrorCode.SERVER_ERROR,
    }
)

# Do not pass Pydantic's generated schema directly to Groq strict mode. This
# intentionally uses only Groq's documented strict-schema subset: closed
# objects, every property required, and a nullable union for `vo`. Beat
# indexes are deliberately absent: ordering is model-generated, while stable
# zero-based identifiers are deterministic application data.
_GROQ_BEAT_PLAN_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "reelproof_beat_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "hook": {"type": "string"},
                "beats": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "concept": {"type": "string"},
                            "caption": {"type": "string"},
                            "vo": {"type": ["string", "null"]},
                        },
                        "required": ["concept", "caption", "vo"],
                        "additionalProperties": False,
                    },
                },
                "suggested_caption": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["hook", "beats", "suggested_caption", "hashtags"],
            "additionalProperties": False,
        },
    },
}


class _GroqBeatPayload(BaseModel):
    """The provider-owned portion of one strict Groq beat response."""

    model_config = ConfigDict(extra="forbid")

    concept: str
    caption: str
    vo: str | None


class _GroqBeatPlanPayload(BaseModel):
    """Strict wire contract before the server assigns stable beat indexes."""

    model_config = ConfigDict(extra="forbid")

    hook: str
    beats: list[_GroqBeatPayload]
    suggested_caption: str
    hashtags: list[str]


def _nvidia_planner_chat(prompt: str):
    """Call NIM with a short, explicit budget and one bounded retry.

    ``genblaze_nvidia.chat`` constructs an OpenAI client with the SDK default
    of two internal retries. A 60-second timeout therefore held failed jobs for
    roughly three minutes. Supplying our own client disables those hidden
    retries so the campaign's configured attempt budget is authoritative.
    """
    attempts = max(1, settings.nvidia_chat_max_attempts)
    timeout = max(1.0, settings.nvidia_chat_timeout_sec)
    base_url = settings.nvidia_chat_base_url or _DEFAULT_NVIDIA_CHAT_BASE_URL
    last_error: ProviderError | None = None

    for attempt in range(1, attempts + 1):
        client = OpenAI(
            api_key=settings.nvidia_api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )
        try:
            return chat(
                settings.nvidia_planner_model,
                system=_SYSTEM,
                prompt=prompt,
                temperature=0.8,
                max_tokens=settings.nvidia_planner_max_tokens,
                response_format=BeatPlan,
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_chat_base_url or None,
                timeout=timeout,
                client=client,
            )
        except ProviderError as exc:
            last_error = exc
            if exc.error_code not in _RETRYABLE_NVIDIA_ERRORS or attempt == attempts:
                raise
            delay = min(
                max(settings.nvidia_chat_retry_backoff_sec, exc.retry_after or 0.0),
                settings.nvidia_chat_max_retry_delay_sec,
            )
            time.sleep(delay)
        finally:
            client.close()

    # The loop always returns or raises; this guards type checkers and protects
    # against a malformed future ProviderError implementation.
    raise last_error or RuntimeError("NVIDIA planner failed without an error")


def _groq_planner_chat(model: str, prompt: str):
    """Use Groq's strict structured-output contract for one planner model."""
    return groq_chat(
        model,
        system=_SYSTEM,
        prompt=prompt,
        temperature=0.1,
        # GPT-OSS's completion budget includes reasoning tokens. Use a
        # lightweight reasoning mode and a safe minimum budget for this short,
        # deterministic plan.
        max_tokens=max(settings.groq_planner_max_tokens, _MIN_GROQ_PLANNER_COMPLETION_TOKENS),
        reasoning_effort="low",
        response_format=_GROQ_BEAT_PLAN_RESPONSE_FORMAT,
        strict_json_schema=True,
        api_key=settings.groq_api_key,
        base_url=settings.groq_chat_base_url or None,
        timeout=settings.groq_chat_timeout_sec,
        max_attempts=max(3, settings.groq_chat_max_attempts),
        retry_backoff_sec=settings.groq_chat_retry_backoff_sec,
        max_retry_delay_sec=settings.groq_chat_max_retry_delay_sec,
    )


def _planner_chat(prompt: str):
    """Dispatch planning and fail over only between equivalent strict models."""
    if settings.llm_provider == "nvidia":
        return _nvidia_planner_chat(prompt)

    models = tuple(
        dict.fromkeys(
            model
            for model in (
                settings.groq_planner_model,
                settings.groq_planner_fallback_model,
            )
            if model
        )
    )
    last_error: ProviderError | None = None
    tried_models: list[str] = []
    for model in models:
        tried_models.append(model)
        try:
            response = _groq_planner_chat(model, prompt)
        except ProviderError as exc:
            last_error = exc
            if exc.error_code not in _GROQ_PLANNER_RETRYABLE_ERRORS:
                raise
            continue

        response.raw["_reelproof_planner_models_tried"] = tried_models
        return response

    raise last_error or RuntimeError("Groq planner failed without an error")


def parse_beat_plan(
    raw: str, beat_count: int, *, assign_indexes_locally: bool = False
) -> BeatPlan:
    """Validate the model response before it can enter the render pipeline."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", maxsplit=2)[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    raw = raw.strip().rstrip("`").strip()

    data = json.loads(raw)
    if assign_indexes_locally:
        payload = _GroqBeatPlanPayload.model_validate(data)
        plan = BeatPlan(
            hook=payload.hook,
            beats=[
                Beat(index=index, concept=beat.concept, caption=beat.caption, vo=beat.vo)
                for index, beat in enumerate(payload.beats)
            ],
            suggested_caption=payload.suggested_caption,
            hashtags=payload.hashtags,
        )
    else:
        plan = BeatPlan.model_validate(data)
    if len(plan.beats) != beat_count:
        raise ValueError(f"Planner returned {len(plan.beats)} beats; expected exactly {beat_count}")

    expected_indexes = list(range(beat_count))
    actual_indexes = [beat.index for beat in plan.beats]
    if actual_indexes != expected_indexes:
        raise ValueError(f"Planner beat indexes must be {expected_indexes}; got {actual_indexes}")

    return plan


def plan_beats(topic: str, beat_count: int = 5, product_context: str | None = None) -> BeatPlan:
    if not settings.active_llm_api_key:
        raise RuntimeError(f"{settings.active_llm_key_env_name} is required to plan a campaign")
    ensure_prompt_allowed(topic)

    user_msg = f"Topic: {topic}\nbeat_count: {beat_count}"
    if product_context:
        user_msg += f"\nProduct context: {product_context}"

    with trace_operation(
        "reelproof.planner",
        inputs={"topic": topic, "beat_count": beat_count, "has_product_context": bool(product_context)},
        metadata={"provider": settings.llm_provider, "model": settings.active_planner_model},
        run_type="llm",
    ) as trace:
        last_error: Exception | None = None
        for attempt in range(1, _GROQ_PLANNER_LOCAL_VALIDATION_ATTEMPTS + 1):
            resp = _planner_chat(user_msg)
            try:
                plan = parse_beat_plan(
                    resp.text,
                    beat_count,
                    assign_indexes_locally=settings.llm_provider == "groq",
                )
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                last_error = exc
                if attempt == _GROQ_PLANNER_LOCAL_VALIDATION_ATTEMPTS:
                    raise RuntimeError(
                        "Planner returned an invalid JSON plan after "
                        f"{_GROQ_PLANNER_LOCAL_VALIDATION_ATTEMPTS} attempts: {exc}"
                    ) from exc
                continue

            raw_response = getattr(resp, "raw", {})
            finish_trace(
                trace,
                {
                    "provider": settings.llm_provider,
                    "model": getattr(resp, "model", settings.active_planner_model),
                    "models_tried": raw_response.get("_reelproof_planner_models_tried"),
                    "response_chars": len(resp.text),
                    "attempts": raw_response.get("_reelproof_attempts", 1),
                    "tokens_in": getattr(resp, "tokens_in", None),
                    "tokens_out": getattr(resp, "tokens_out", None),
                },
            )
            return plan

    raise last_error or RuntimeError("Planner failed without an error")
