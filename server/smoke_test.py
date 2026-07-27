"""Phase 1 preflight and opt-in live smoke test.

Run from ``server/`` using the project's Conda environment:

    conda run -n myenv python smoke_test.py
    conda run -n myenv python smoke_test.py --live

The default command never calls a paid provider. ``--live`` proves the
Phase 1 image -> B2 -> verified-manifest and music primitives using the
credentials in ``server/.env``.

GenBlaze's FFmpegCompositor accepts a *video* and an audio asset, not an
image and an audio asset. The actual compositor proof belongs to Phase 2,
once the slideshow builder turns the stills into a video stream.
"""

from __future__ import annotations

import argparse
import shutil
import sys


def report(label: str, ok: bool, detail: str = "") -> bool:
    status = "OK" if ok else "FAIL"
    print(f"  [{status:4}] {label}" + (f": {detail}" if detail else ""))
    return ok


def preflight() -> bool:
    """Run local checks only; no network calls and no paid inference."""
    from app.config import settings
    from app.engine.captions import caption_renderer_error

    print("\n=== ReelProof Phase 1 preflight ===\n")
    ok = True

    missing = settings.missing_phase1_settings()
    ok &= report(
        "Phase 1 credentials configured",
        not missing,
        "missing " + ", ".join(missing) if missing else "",
    )

    ffmpeg = shutil.which("ffmpeg")
    ok &= report("ffmpeg on PATH", ffmpeg is not None, ffmpeg or "install ffmpeg before Phase 2")
    renderer_error = caption_renderer_error()
    ok &= report(
        "ffmpeg caption renderer",
        renderer_error is None,
        renderer_error or "drawtext filter available",
    )

    try:
        import genblaze_core  # noqa: F401
        import genblaze_gmicloud  # noqa: F401
        import genblaze_openai  # noqa: F401
        import genblaze_s3  # noqa: F401
    except ImportError as exc:
        ok &= report("required GenBlaze packages import", False, str(exc))
    else:
        ok &= report("required GenBlaze packages import", True)

    print(
        "\nUse --live only after the checks above pass; it makes one image and one music request.\n"
    )
    return bool(ok)


def live_smoke() -> bool:
    """Make the two paid Phase 1 provider calls and verify B2 persistence."""
    from genblaze_core import Modality, Pipeline
    from genblaze_core.providers import per_unit
    from genblaze_gmicloud import GMICloudImageProvider

    from app.config import settings
    from app.engine.stability_audio import StabilityAudioProvider
    from app.storage import build_sink

    if missing := settings.missing_phase1_settings():
        report("live smoke prerequisites", False, "missing " + ", ".join(missing))
        return False
    if not shutil.which("ffmpeg"):
        report("live smoke prerequisites", False, "ffmpeg is not on PATH")
        return False

    print("=== Phase 1 live smoke (paid provider calls) ===\n")
    try:
        sink = build_sink()  # B2 credential/bucket preflight happens here.
        report("B2 backend preflight", True)

        image = GMICloudImageProvider(api_key=settings.gmi_api_key)
        # GMI rates are user-supplied. Update the .env value if your account's
        # contract differs from the documented Reve Create per-image rate.
        image.models.register_pricing(
            settings.gmi_image_model, per_unit(settings.gmi_image_unit_cost_usd)
        )
        image_result = (
            Pipeline("phase1-image-b2")
            .step(
                image,
                model=settings.gmi_image_model,
                prompt="A clean faceless product flat lay on a warm studio background, no text",
                modality=Modality.IMAGE,
            )
            .run(sink=sink, timeout=120)
        )
        image_verified = image_result.manifest.verify()
        report("image -> B2 -> manifest.verify()", image_verified, image_result.run.run_id)

        music = StabilityAudioProvider(api_key=settings.stability_api_key)
        music_result = (
            Pipeline("phase1-music-b2")
            .step(
                music,
                model="stable-audio-2.5",
                prompt="A short, warm instrumental music bed for a product reel. No vocals.",
                modality=Modality.AUDIO,
                duration=5,
            )
            .run(sink=sink, timeout=120)
        )
        music_verified = music_result.manifest.verify()
        report("music -> B2 -> manifest.verify()", music_verified, music_result.run.run_id)

        print(
            "\nPhase 1 live primitives passed."
            if image_verified and music_verified
            else "\nPhase 1 live primitives failed."
        )
        return bool(image_verified and music_verified)
    except Exception as exc:
        report("Phase 1 live smoke", False, str(exc))
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="ReelProof Phase 1 checks")
    parser.add_argument(
        "--live", action="store_true", help="run paid image and music provider checks"
    )
    args = parser.parse_args()

    passed = preflight()
    if args.live and passed:
        passed = live_smoke() and passed
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
