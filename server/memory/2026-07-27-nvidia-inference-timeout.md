# NVIDIA inference timeout investigation — 2026-07-27

## Symptom

Campaign planner calls fail with `NVIDIA chat failed: Request timed out.`

## Root cause

The application configuration is valid: `NVIDIA_API_KEY` is present and has the expected `nvapi-` prefix, the default `https://integrate.api.nvidia.com/v1` endpoint is selected, and `meta/llama-3.3-70b-instruct` is a currently hosted NVIDIA NIM model.

An authenticated `GET /v1/models` returned HTTP 200. A direct OpenAI-compatible call to `/v1/chat/completions` using that model, one user message (`Reply with OK.`), `max_tokens=16`, a 20-second timeout, and zero retries connected successfully but timed out waiting for response headers (`httpx.ReadTimeout`). This excludes credentials, DNS/proxy configuration, the campaign prompt, structured output, and the LangSmith wrapper.

The failure is therefore an NVIDIA inference-side stall or queue delay for the hosted model. It did not return an HTTP 401, 404, 429, or 5xx response.

## GenBlaze review

The installed `genblaze-nvidia==0.3.1` documentation describes `chat()` as a thin OpenAI-wire-compatible helper. Its implementation builds `openai.OpenAI(api_key, base_url, timeout)` and calls `client.chat.completions.create(**payload)`. The raw probe used that same SDK and request path, so the timeout is not introduced by GenBlaze.

`NvidiaChatProvider` is suitable when the chat call must be a GenBlaze pipeline step with manifests and provider retry policy, but it invokes the same `/v1/chat/completions` transport. Replacing the standalone planner helper with that provider would improve provenance, not the upstream inference response time.

## Related configuration

`NVIDIA_CHAT_TIMEOUT_SEC=60` and `NVIDIA_CHAT_MAX_ATTEMPTS=3` currently override the safer repository defaults, so one blocked planner can occupy the worker for roughly three minutes plus backoff.

LangSmith is separately mis-scoped: its configured workspace ID returns HTTP 403 for the readable `reelproof` project, while the same key can read that project when the workspace ID is omitted. This affects trace export only, not NVIDIA requests.

## Status

BLOCKED on NVIDIA hosted inference responsiveness. No application change was applied because the smallest raw request reproduces the upstream timeout.
