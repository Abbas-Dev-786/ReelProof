# Stability audio output must stay under GenBlaze allowed roots

Date: 2026-07-28

Symptom:
- `stability-audio:stable-audio-2.5` completed, but asset transfer failed with:
  `Access denied: local file path C:\Users\abbas\OneDrive\Desktop\backblaze\server is outside allowed directories. Files must be under temp or output_dir.`

Root cause:
- There were two related issues:
  1. `generate_music_asset()` instantiated `StabilityAudioProvider` without an explicit `output_dir`.
  2. `genblaze-stability-audio==0.3.1` builds Windows file URLs as `file://{quote(str(path))}`. For a Windows path like `C:\...`, this becomes `file://C%3A%5C...`; `urlparse()` treats the encoded drive/path as the URL host and leaves `path` empty. GenBlaze then resolves `Path("")` to the process working directory, which produced the rejected `...\backblaze\server` path.

Fix:
- `server/app/engine/audio.py` now resolves music output via the active `media_workspace()` context and passes `output_dir=<workspace>/music` to `StabilityAudioProvider`.
- Outside an active workspace, it falls back to an OS temp-backed `reelproof-music` workspace.
- `server/app/engine/stability_audio.py` now normalizes malformed Windows `file://C%3A%5C...` URLs to valid `file:///C:/...` URLs before asset transfer.

Verification:
- `cd server && .venv/bin/ruff check app tests smoke_test.py`
- `cd server && .venv/bin/ruff format --check app/engine/audio.py tests/test_stability_audio.py`
- `cd server && .venv/bin/python -m unittest discover -s tests`
