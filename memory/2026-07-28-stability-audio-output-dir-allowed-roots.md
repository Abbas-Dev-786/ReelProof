# Stability audio output must stay under GenBlaze allowed roots

Date: 2026-07-28

Symptom:
- `stability-audio:stable-audio-2.5` completed, but asset transfer failed with:
  `Access denied: local file path C:\Users\abbas\OneDrive\Desktop\backblaze\server is outside allowed directories. Files must be under temp or output_dir.`

Root cause:
- `generate_music_asset()` instantiated `StabilityAudioProvider` without an explicit `output_dir`.
- GenBlaze asset transfer only accepts local files under the run temp workspace or provider `output_dir`; provider-emitted local files outside those roots are rejected.

Fix:
- `server/app/engine/audio.py` now resolves music output via the active `media_workspace()` context and passes `output_dir=<workspace>/music` to `StabilityAudioProvider`.
- Outside an active workspace, it falls back to an OS temp-backed `reelproof-music` workspace.

Verification:
- `cd server && .venv/bin/ruff check app tests smoke_test.py`
- `cd server && .venv/bin/ruff format --check app/engine/audio.py tests/test_stability_audio.py`
- `cd server && .venv/bin/python -m unittest discover -s tests`
