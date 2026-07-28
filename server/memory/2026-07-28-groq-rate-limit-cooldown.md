# Groq rate-limit cooldown fix — 2026-07-28

## Symptom

Campaign failed in the vision judge with:

```text
Groq chat failed: Error code: 429 - ... tokens per minute (TPM):
Limit 8000, Used 5523, Requested 2709. Please try again in 1.74s.
```

## Root cause

`app.engine.groq.chat()` already retried retryable Groq errors and honored
standard `Retry-After` headers. Groq's OpenAI-compatible 429 error in this
case carried the cooldown only in the exception body text (`Please try again in
1.74s`), so `retry_after_from_response(exc)` returned `None`. The helper fell
back to the generic retry delay and could exhaust attempts before the actual
TPM window recovered.

The vision judge also requested 512 completion tokens even though the expected
response is a small JSON object, adding avoidable TPM pressure.

## Fix

- Added `_retry_after_from_groq_error()` to parse cooldowns from both headers
  and Groq body text.
- Added a 0.5 second safety buffer to parsed cooldowns.
- Reduced `groq_vision_max_tokens` default from 512 to 256.
- Added an in-process, per-model Groq token pacer for the vision judge. The
  default uses the observed free-tier limit (`8000` TPM), reserves an estimated
  `2500` tokens per judge call, and spaces repeated Qwen vision requests using
  a `0.9` safety factor. Provider 429 cooldowns are also shared into this
  pacer so the next local call waits before submitting.
- Added regression coverage for the exact body-message cooldown format.

## Verification

- `python -m unittest discover -s tests -v`: 56 passing.
- `ruff check app tests smoke_test.py`: passing.
