# Cloudflare image output directory allowed-root fix — 2026-07-28

## Symptom

Cloudflare image generation succeeded, but B2 asset transfer failed:

```text
Asset transfer failed ... Access denied: local file path
C:\Users\abbas\OneDrive\Desktop\backblaze\server\output\cloudflare-images\...
is outside allowed directories. Files must be under temp or output_dir.
```

## Root cause

`app.engine.images.image_provider()` constructed `CloudflareImageProvider` with
`output_dir=settings.output_path / "cloudflare-images"`. On Windows this saved
provider output under the repository's `server/output` directory. The installed
GenBlaze `AssetTransfer` allowlist accepts local file uploads only from the OS
temporary directory by default, so the generated `file://` asset was rejected
when `ObjectStorageSink` tried to transfer it to B2.

This repeated the same class of issue documented in
`memory/2026-07-27-genblaze-local-media-workspace.md`: transient media must be
staged inside `media_workspace()`, not under the repo output directory.

## Fix

- `app.workspace.media_workspace()` now stores the active temp workspace in a
  `ContextVar`.
- `app.workspace.current_media_workspace()` exposes that workspace to provider
  factories.
- `app.engine.images._cloudflare_output_dir()` writes Cloudflare outputs under
  the active media workspace's `cloudflare-images/` subdirectory. Outside a
  campaign context, it falls back to a stable directory under the OS temp root.

## Verification

- `tests.test_media_workspace` asserts the active workspace context is set and
  reset.
- `tests.test_phase7` asserts Cloudflare image provider output is inside the
  active media workspace.
- `python -m unittest discover -s tests -v`: 53 passing.
- `ruff check app tests smoke_test.py`: passing.
