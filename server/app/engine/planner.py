from __future__ import annotations

import json
import time

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_nvidia import chat
from openai import OpenAI

from ..config import settings
from ..observability import finish_trace, trace_operation
from ..schemas import Beat, BeatPlan
from .groq import chat as groq_chat
from .safety import ensure_prompt_allowed

_SYSTEM = """\
You are a faceless short-form content strategist. Given a topic, produce a beat plan for a
9:16 vertical social video (TikTok/Reels style). Reply ONLY with valid JSON matching this schema:

{
  "hook": "<one-line attention-grabbing opener>",
  "beats": [
    {
      "index": 0,
      "concept": "<visual scene description for image generation>",
      "caption": "<short on-screen text, max 8 words>",
      "vo": "<optional voiceover line, or null>"
    }
  ],
  "suggested_caption": "<post caption with emojis>",
  "hashtags": ["tag1", "tag2"]
}

Rules:
- concept must describe a clean, photorealistic, faceless scene (no people's faces)
- caption must be legible on a dark background; use title case; max 8 words
- 3-8 beats depending on beat_count param
- hashtags: 5-10 relevant tags without the # symbol
"""

_DEFAULT_NVIDIA_CHAT_BASE_URL = "https://integrate.api.nvidia.com/v1"
_RETRYABLE_NVIDIA_ERRORS = frozenset(
    {
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.RATE_LIMIT,
        ProviderErrorCode.SERVER_ERROR,
    }
)


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


def _planner_chat(prompt: str):
    """Dispatch planning to the explicitly selected LLM provider."""
    if settings.llm_provider == "nvidia":
        return _nvidia_planner_chat(prompt)
    return groq_chat(
        settings.groq_planner_model,
        system=_SYSTEM,
        prompt=prompt,
        temperature=0.8,
        max_tokens=settings.groq_planner_max_tokens,
        response_format=BeatPlan,
        strict_json_schema=True,
        api_key=settings.groq_api_key,
        base_url=settings.groq_chat_base_url or None,
        timeout=settings.groq_chat_timeout_sec,
        max_attempts=settings.groq_chat_max_attempts,
        retry_backoff_sec=settings.groq_chat_retry_backoff_sec,
        max_retry_delay_sec=settings.groq_chat_max_retry_delay_sec,
    )


def parse_beat_plan(raw: str, beat_count: int) -> BeatPlan:
    """Validate the model response before it can enter the render pipeline."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", maxsplit=2)[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    raw = raw.strip().rstrip("`").strip()

    data = json.loads(raw)
    beats = [Beat(**beat) for beat in data["beats"]]
    if len(beats) != beat_count:
        raise ValueError(f"Planner returned {len(beats)} beats; expected exactly {beat_count}")

    expected_indexes = list(range(beat_count))
    actual_indexes = [beat.index for beat in beats]
    if actual_indexes != expected_indexes:
        raise ValueError(f"Planner beat indexes must be {expected_indexes}; got {actual_indexes}")

    return BeatPlan(
        hook=data["hook"],
        beats=beats,
        suggested_caption=data["suggested_caption"],
        hashtags=data.get("hashtags", []),
    )


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
        resp = _planner_chat(user_msg)
        raw_response = getattr(resp, "raw", {})
        finish_trace(
            trace,
            {
                "provider": settings.llm_provider,
                "model": getattr(resp, "model", settings.active_planner_model),
                "response_chars": len(resp.text),
                "attempts": raw_response.get("_reelproof_attempts", 1),
                "tokens_in": getattr(resp, "tokens_in", None),
                "tokens_out": getattr(resp, "tokens_out", None),
            },
        )

    return parse_beat_plan(resp.text, beat_count)
