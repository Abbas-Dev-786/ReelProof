# Groq strict-schema validation failure — 2026-07-27

- **Symptom:** Showcase planning failed with Groq HTTP 400 `json_validate_failed`, including an empty `failed_generation` field.
- **Root cause:** The planner sent the Pydantic `BeatPlan` through Groq strict JSON-schema mode. The provider-side strict decoder intermittently rejected the request before returning model content, even after increasing the completion budget.
- **Fix:** The planner now uses Groq JSON Object mode, a low reasoning effort, and a 4,096-token minimum. Local Pydantic parsing remains the schema boundary and retries one malformed JSON object. Groq `json_validate_failed` errors are treated as retryable.
- **Related prevention:** Campaign startup and `smoke_test.py` now require an `ffmpeg` build with the `drawtext` filter before paid generation begins.
- **Verification:** One live Groq-only one-beat plan succeeded with the updated path; all 45 server tests and Ruff pass.
