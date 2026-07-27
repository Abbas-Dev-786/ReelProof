# GenBlaze local-media workspace fix

## Symptom

On Windows, `pregenerate_showcases.py` failed after caption rendering with:

```text
Access denied: local file path ...\\server\\output\\<job-id>\\beat_00_captioned.png
is outside allowed directories.
```

## Root cause

`ObjectStorageSink` in the installed `genblaze-core` release delegates local
`file://` uploads to `AssetTransfer`. That transfer only permits the OS
temporary directory by default. The sink does not expose `allowed_roots`, so
the app's persistent `server/output` directory cannot be registered safely.

The same incorrect staging location could affect caption frames, final reels,
ElevenLabs voiceovers, and product uploads.

## Resolution

`app.workspace.media_workspace()` creates a unique `TemporaryDirectory` under
the operating system temp root and removes it after use. Campaign rendering and
product-upload staging now run inside that workspace. Voiceover generation
requires and validates the same workspace. The app does not alter GenBlaze's
allowlist or reach into its private sink implementation.

## Verification

- A regression test performs a real `AssetTransfer` from an app workspace.
- Campaign and product-upload tests assert temp-root placement and cleanup.
- `unittest discover -s tests -v`: 48 passing.
- `ruff check app tests`: passing.
- `mypy app main.py` has one existing unrelated error in
  `app/observability.py` for the `trace(..., run_type=...)` annotation.
