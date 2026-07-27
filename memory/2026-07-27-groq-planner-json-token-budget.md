# Groq strict JSON completion budget — 2026-07-27

- **Symptom:** Showcase planning failed with Groq HTTP 400 `json_validate_failed`; `failed_generation` reported that max completion tokens were reached before valid JSON was produced.
- **Root cause:** The GPT-OSS planner used its default medium reasoning effort with a 2,048-token completion cap. Reasoning tokens could exhaust that cap before Groq's strict JSON decoder emitted the complete `BeatPlan` document.
- **Fix:** The planner now requests GPT-OSS `reasoning_effort="low"` and enforces a 4,096-token minimum completion budget. The Groq adapter forwards the reasoning setting only when requested.
- **Regression coverage:** Tests assert that the adapter includes `reasoning_effort` in its request and the planner uses the low-effort, 4,096-token minimum path.
- **Verification:** All 43 server tests and Ruff pass.
