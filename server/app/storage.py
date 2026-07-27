from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from genblaze_core import KeyStrategy, Manifest, ObjectLockConfig, ObjectStorageSink
from genblaze_s3 import S3StorageBackend

from .config import settings

_VISION_URL_TTL_SEC = 900


@lru_cache(maxsize=1)
def get_backend() -> S3StorageBackend:
    """Cached B2 backend — constructed once, reused across requests."""
    missing = [
        name
        for name, value in {
            "B2_KEY_ID": settings.b2_key_id,
            "B2_APP_KEY": settings.b2_app_key,
            "B2_BUCKET": settings.b2_bucket,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"B2 is not configured; set {', '.join(missing)}")

    return S3StorageBackend.for_backblaze(
        settings.b2_bucket,
        region=settings.b2_region,
        key_id=settings.b2_key_id,
        app_key=settings.b2_app_key,
        public_url_base=settings.b2_public_url_base or None,
        auto_lifecycle=True,
    )


def build_sink() -> ObjectStorageSink:
    """New sink per run — ObjectStorageSink is not reentrant across runs."""
    parquet_sink = None
    if settings.parquet_enabled:
        # Parquet is valuable for the Phase 3 lineage graph, but it is an
        # optional GenBlaze dependency (pyarrow) and must not block Phase 1.
        from genblaze_core import ParquetSink

        settings.data_path.mkdir(parents=True, exist_ok=True)
        parquet_sink = ParquetSink(settings.data_path)

    lock_config = None
    if settings.b2_object_lock_enabled:
        lock_config = ObjectLockConfig(
            retain_until=datetime.now(UTC) + timedelta(days=settings.b2_object_lock_retention_days),
            mode="GOVERNANCE",
        )

    return ObjectStorageSink(
        get_backend(),
        prefix="reelproof",
        key_strategy=KeyStrategy.HIERARCHICAL,
        parquet_sink=parquet_sink,
        manifest_lock=lock_config,
    )


def readable_asset_url(asset_url: str) -> str:
    """Return a short-lived readable URL when an asset belongs to this B2 bucket.

    Third-party providers and local ffmpeg assembly cannot read a private B2
    object through its durable browser URL. The durable URL remains in
    manifests; only the immediate reader receives this signed URL.
    """
    backend = get_backend()
    key = backend.key_from_url(asset_url)
    if key is None:
        return asset_url
    return backend.presigned_get_url(key, expires_in=_VISION_URL_TTL_SEC)


def verify_manifest_json(manifest_json: str) -> dict[str, Any]:
    """Read a persisted manifest from B2 and validate its canonical hash."""
    try:
        recorded_manifest = Manifest.model_validate_json(manifest_json)
        if recorded_manifest.run is None:
            raise ValueError("Manifest has no run record")

        # Use the run's hierarchical key to fetch the B2 copy. The SDK then
        # verifies the canonical manifest and declared asset hashes.
        manifest = build_sink().read_manifest(recorded_manifest.run, verify=True)
        steps = manifest.run.steps
        first_step = steps[0] if steps else None
        return {
            "run_id": manifest.run.run_id,
            "verified": manifest.verify(),
            "manifest_hash": manifest.canonical_hash,
            "manifest_uri": manifest.manifest_uri,
            "provider": first_step.provider if first_step else None,
            "model": first_step.model if first_step else None,
            "created_at": manifest.run.started_at.isoformat() if manifest.run.started_at else None,
            "parent_run_id": manifest.run.parent_run_id,
        }
    except Exception as exc:
        return {"verified": False, "error": str(exc)}
