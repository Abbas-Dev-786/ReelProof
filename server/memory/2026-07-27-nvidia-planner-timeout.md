# NVIDIA planner timeout investigation — 2026-07-27

## Symptom

The only two stored campaign jobs failed at the planner step with `NVIDIA chat failed: Request timed out.` Both have no provenance records.

## Root cause

The configured model ID (`z-ai/glm-5.2`) and NVIDIA default endpoint are valid. `genblaze_nvidia.chat` creates an OpenAI client with its default two retries and a 60-second timeout. The application supplied neither a planner timeout, output-token limit, nor retry policy. The recorded jobs each remained in the planner for roughly three minutes, which matches three 60-second SDK attempts.

## Fix

The planner now uses a client with SDK retries disabled, two application-level attempts of 30 seconds each, a retry wait capped at five seconds, and a 2048-token response cap. Only timeout, rate-limit, and server errors retry. Campaigns also fail before provider calls when browser-playable B2 configuration is incomplete.

## Evidence

`python -m unittest discover -s tests -v` passed (31 tests), including a regression test that simulates a timeout followed by success and asserts `max_retries=0` on each client.

## Live verification status

Blocked in this workspace: `NVIDIA_API_KEY`, `GMI_API_KEY`, `STABILITY_API_KEY`, `B2_KEY_ID`, `B2_APP_KEY`, and `B2_PUBLIC_URL_BASE` are absent; `ffmpeg` is not on `PATH`.
