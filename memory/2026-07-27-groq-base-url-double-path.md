# Groq chat endpoint double-path — 2026-07-27

- **Symptom:** A showcase campaign failed with Groq HTTP 404: `Unknown request URL: POST /openai/v1/chat/completions/chat/completions`.
- **Root cause:** `GROQ_CHAT_BASE_URL` was set to the complete chat endpoint. The OpenAI-compatible SDK appends `/chat/completions`, duplicating that suffix.
- **Fix:** Set the local setting to the API root (`https://api.groq.com/openai/v1`) and make `app.engine.groq` normalize an accidentally supplied full chat endpoint for backward compatibility.
- **Regression coverage:** `tests/test_groq.py` asserts the adapter gives the SDK the API root when passed a complete chat endpoint.
- **Verification:** The regression test, all 40 server tests, and Ruff completed successfully.
