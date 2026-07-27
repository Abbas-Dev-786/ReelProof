# Showcase pre-generation connection failure — 2026-07-27

- **Symptom:** `scripts/pregenerate_showcases.py` raised `httpx.ConnectError: [Errno 61] Connection refused` while requesting `/health`.
- **Root cause:** The runner defaults to `http://127.0.0.1:8000`, but no process was listening on TCP port 8000. The script intentionally checks API health before it creates any campaign.
- **Evidence:** `lsof -nP -iTCP:8000 -sTCP:LISTEN` returned no listeners. `server/README.md` documents starting `uvicorn main:app --reload --port 8000` in another shell before running the script.
- **Resolution:** Start the API on port 8000, or pass `--base-url` / set `REELPROOF_API_URL` to a running API.
- **Code changes:** None. This was an unmet runtime prerequisite, not a script defect.
