# Stability Audio multipart request fix — 2026-07-27

## DEBUG REPORT

- **Symptom:** A Stable Audio campaign step failed with HTTP 400 and
  `content-type: must be multipart/form-data`.
- **Root cause:** The installed `genblaze-stability-audio==0.3.1` provider
  calls `httpx.Client.post(data=...)`. HTTPX serializes that as
  `application/x-www-form-urlencoded`, while Stability's Stable Audio
  text-to-audio endpoint accepts only multipart form fields.
- **Fix:** Added `app.engine.stability_audio.StabilityAudioProvider`, a narrow
  compatibility subclass that keeps GenBlaze's generation/provenance flow and
  adapts its outbound form fields to HTTPX multipart entries. Campaign audio
  generation and the paid live smoke check now import this provider.
- **Evidence:** The new mock-transport regression test captures an outgoing
  `multipart/form-data; boundary=...` request and verifies prompt, duration,
  output format, seed, authorization, and `Accept` header preservation.
- **Regression test:** `server/tests/test_stability_audio.py`.
- **Verification:** `unittest discover -s tests -v` completed with 50 passing
  tests; Ruff passed. No paid Stability request was made during verification.
- **Related:** The upstream connector is intentionally wrapped rather than
  edited inside `server/.venv`, so redeploying dependencies retains the fix.
- **Status:** DONE.
