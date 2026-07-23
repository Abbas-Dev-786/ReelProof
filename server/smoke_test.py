"""
Phase 0/1 smoke test — run from server/ with the venv active:
    python smoke_test.py

Verifies:
  1. Config loads (env vars present)
  2. B2 backend connects
  3. One image generation + B2 store + manifest.verify()
  4. FFmpegCompositor is importable and ffmpeg is on PATH
"""

from __future__ import annotations

import subprocess
import sys


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "OK " if ok else "FAIL"
    print(f"  [{status}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        sys.exit(1)


print("\n=== ReelProof Phase 0/1 Smoke Test ===\n")

# 1. Config
print("1. Config")
from app.config import settings
check("OPENAI_API_KEY set", bool(settings.openai_api_key), "(not set = judge/planner won't work)")
check("GMI_API_KEY set", bool(settings.gmi_api_key))
check("B2_KEY_ID set", bool(settings.b2_key_id))
check("B2_APP_KEY set", bool(settings.b2_app_key))
check("B2_BUCKET set", bool(settings.b2_bucket), settings.b2_bucket)

# 2. ffmpeg
print("\n2. ffmpeg")
r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
ver = r.stdout.splitlines()[0] if r.returncode == 0 else ""
check("ffmpeg on PATH", r.returncode == 0, ver[:60])

# 3. Genblaze imports
print("\n3. Genblaze packages")
import genblaze_core, genblaze_s3, genblaze_openai, genblaze_gmicloud
import genblaze_stability_audio
check("genblaze_core", True)
check("genblaze_s3", True)
check("genblaze_openai", True)
check("genblaze_gmicloud", True)
check("genblaze_stability_audio", True)

# 4. B2 backend connection
print("\n4. B2 connection")
try:
    from app.storage import get_backend
    backend = get_backend()
    check("S3StorageBackend.for_backblaze() init", True)
except Exception as e:
    check("S3StorageBackend.for_backblaze() init", False, str(e))

# 5. GMICloud image + B2 store (live API call — skipped if no keys)
print("\n5. Live: GMICloud image → B2 (skip if no keys)")
if settings.gmi_api_key and settings.b2_key_id:
    try:
        from genblaze_core import Modality, Pipeline
        from genblaze_gmicloud import GMICloudImageProvider
        from app.storage import build_sink

        sink = build_sink()
        result = (
            Pipeline("smoke-test")
            .step(
                GMICloudImageProvider(api_key=settings.gmi_api_key),
                model="reve-create",
                prompt="a serene mountain lake at sunrise, photorealistic, no text",
                modality=Modality.IMAGE,
            )
            .run(sink=sink, timeout=120)
        )
        verified = result.manifest.verify()
        url = result.run.steps[0].assets[0].url if result.run.steps[0].assets else "n/a"
        check("image generated", True, url[:80])
        check("manifest.verify()", verified)
        print(f"     run_id:  {result.run.run_id}")
        print(f"     hash:    {result.manifest.canonical_hash[:24]}...")
    except Exception as e:
        check("GMICloud image → B2", False, str(e))
else:
    print("  [SKIP] GMI_API_KEY or B2 keys not set")

print("\n=== Done ===\n")
