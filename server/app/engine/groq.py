"""Bounded, observable chat calls for Groq's OpenAI-compatible API."""

from __future__ import annotations

import copy
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.chat import ChatMessage, ChatResponse, ToolCall, coerce_response_format
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.providers.retry import retry_after_from_response
from openai import OpenAI

from ..observability import finish_trace, trace_operation

DEFAULT_CHAT_BASE_URL = "https://api.groq.com/openai/v1"
_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"
_RETRYABLE_ERRORS = frozenset(
    {
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.RATE_LIMIT,
        ProviderErrorCode.SERVER_ERROR,
    }
)


def _api_base_url(base_url: str | None) -> str:
    """Return the API root expected by the OpenAI-compatible client.

    The OpenAI SDK appends ``/chat/completions`` when invoking the chat API.
    Accepting a copied full endpoint here avoids producing the invalid doubled
    path ``.../chat/completions/chat/completions``.
    """
    value = (base_url or DEFAULT_CHAT_BASE_URL).strip().rstrip("/")
    if value.endswith(_CHAT_COMPLETIONS_SUFFIX):
        return value[: -len(_CHAT_COMPLETIONS_SUFFIX)]
    return value


def _trace_safe_value(value: Any) -> Any:
    """Redact query strings while preserving enough URL context for traces."""
    if isinstance(value, dict):
        return {key: _trace_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_trace_safe_value(item) for item in value]
    if isinstance(value, str):
        parsed = urlsplit(value)
        if parsed.scheme and parsed.netloc and parsed.query:
            return urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, "redacted=1", parsed.fragment)
            )
    return value


def _normalize_messages(
    messages: list[ChatMessage] | list[dict[str, Any]] | None,
    prompt: str | None,
    system: str | None,
) -> list[dict[str, Any]]:
    if messages is None and prompt is None:
        raise ProviderError(
            "Groq chat requires either messages or prompt", error_code=ProviderErrorCode.INVALID_INPUT
        )

    normalized: list[dict[str, Any]] = []
    if system is not None:
        normalized.append({"role": "system", "content": system})
    if messages is None:
        normalized.append({"role": "user", "content": prompt})
        return normalized

    for message in messages:
        if isinstance(message, ChatMessage):
            content: Any
            if isinstance(message.content, str):
                content = message.content
            else:
                content = [block.model_dump(exclude_none=True) for block in message.content]
            normalized.append({"role": message.role, "content": content})
        else:
            normalized.append(dict(message))
    return normalized


def _make_schema_strict(value: Any) -> Any:
    """Make Pydantic JSON Schema compatible with Groq strict-output rules.

    Groq requires every object property to be listed in ``required`` and does
    not allow unspecified properties in strict mode. Optional Pydantic fields
    are nullable in the emitted schema, so making them required preserves their
    ``null`` value while satisfying the wire contract.
    """
    if isinstance(value, list):
        return [_make_schema_strict(item) for item in value]
    if not isinstance(value, dict):
        return value

    strict_value = {key: _make_schema_strict(item) for key, item in value.items()}
    properties = strict_value.get("properties")
    if isinstance(properties, dict):
        strict_value["required"] = list(properties)
        strict_value["additionalProperties"] = False
    return strict_value


def _response_format(response_format: dict[str, Any] | type | None, *, strict: bool) -> dict[str, Any] | None:
    if response_format is None:
        return None
    envelope = copy.deepcopy(coerce_response_format(response_format))
    json_schema = envelope.get("json_schema")
    if isinstance(json_schema, dict):
        json_schema["strict"] = strict
        if strict and isinstance(json_schema.get("schema"), dict):
            json_schema["schema"] = _make_schema_strict(json_schema["schema"])
    return envelope


def _error_code(exc: Exception) -> ProviderErrorCode:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    message = str(exc).lower()
    if status_code == 429:
        return ProviderErrorCode.RATE_LIMIT
    if status_code in (401, 403):
        return ProviderErrorCode.AUTH_FAILURE
    if status_code == 404:
        return ProviderErrorCode.MODEL_ERROR
    if status_code == 400:
        # JSON Object mode can occasionally fail before producing content.
        # Groq labels this a 400, but retrying is the documented recovery.
        if "json_validate_failed" in message:
            return ProviderErrorCode.SERVER_ERROR
        return ProviderErrorCode.INVALID_INPUT
    if isinstance(status_code, int) and status_code >= 500:
        return ProviderErrorCode.SERVER_ERROR

    if "timeout" in message or "timed out" in message:
        return ProviderErrorCode.TIMEOUT
    if "rate limit" in message or "too many requests" in message:
        return ProviderErrorCode.RATE_LIMIT
    if "connection" in message or "temporarily unavailable" in message:
        return ProviderErrorCode.SERVER_ERROR
    return ProviderErrorCode.UNKNOWN


def _parse_response(model: str, raw: Any) -> ChatResponse:
    raw_dict = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
    choice = raw_dict.get("choices", [{}])[0]
    message = choice.get("message", {}) or {}
    usage = raw_dict.get("usage", {}) or {}

    tool_calls: list[ToolCall] = []
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function", {}) or {}
        tool_calls.append(
            ToolCall(
                id=tool_call.get("id", ""),
                name=function.get("name", ""),
                arguments=function.get("arguments", {}),
            )
        )

    return ChatResponse(
        text=message.get("content") or "",
        model=raw_dict.get("model", model),
        finish_reason=choice.get("finish_reason"),
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        tokens_cached=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        tool_calls=tool_calls,
        raw=raw_dict,
    )


def chat(
    model: str,
    messages: list[ChatMessage] | list[dict[str, Any]] | None = None,
    *,
    prompt: str | None = None,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    response_format: dict[str, Any] | type | None = None,
    strict_json_schema: bool = True,
    api_key: str,
    base_url: str | None = None,
    timeout: float = 30.0,
    max_attempts: int = 2,
    retry_backoff_sec: float = 1.0,
    max_retry_delay_sec: float = 5.0,
) -> ChatResponse:
    """Call Groq without hidden SDK retries and record every physical attempt."""
    if not api_key:
        raise ProviderError(
            "GROQ_API_KEY is required for Groq chat", error_code=ProviderErrorCode.AUTH_FAILURE
        )

    wire_messages = _normalize_messages(messages, prompt, system)
    payload: dict[str, Any] = {"model": model, "messages": wire_messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        # Groq's current Chat Completions examples use this OpenAI parameter
        # for both GPT-OSS and the Qwen vision model.
        payload["max_completion_tokens"] = max_tokens
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    if wire_format := _response_format(response_format, strict=strict_json_schema):
        payload["response_format"] = wire_format

    attempts = max(1, max_attempts)
    timeout = max(1.0, timeout)
    last_error: ProviderError | None = None
    for attempt in range(1, attempts + 1):
        with trace_operation(
            "reelproof.groq.chat",
            inputs={"model": model, "messages": _trace_safe_value(wire_messages)},
            metadata={
                "provider": "groq",
                "model": model,
                "attempt": attempt,
                "strict_json_schema": strict_json_schema,
            },
            run_type="llm",
        ) as trace:
            client = OpenAI(
                api_key=api_key,
                base_url=_api_base_url(base_url),
                timeout=timeout,
                max_retries=0,
            )
            try:
                response = _parse_response(model, client.chat.completions.create(**payload))
                response.raw["_reelproof_attempts"] = attempt
                response.raw["_reelproof_provider"] = "groq"
                finish_trace(
                    trace,
                    {
                        "model": response.model,
                        "attempt": attempt,
                        "tokens_in": response.tokens_in,
                        "tokens_out": response.tokens_out,
                    },
                )
                return response
            except Exception as exc:
                last_error = ProviderError(
                    f"Groq chat failed: {exc}",
                    error_code=_error_code(exc),
                    retry_after=retry_after_from_response(exc),
                    attempts=attempt,
                )
            finally:
                client.close()

        if last_error.error_code not in _RETRYABLE_ERRORS or attempt == attempts:
            raise last_error
        delay = min(
            max(retry_backoff_sec, last_error.retry_after or 0.0), max_retry_delay_sec
        )
        time.sleep(delay)

    raise last_error or RuntimeError("Groq chat failed without an error")
