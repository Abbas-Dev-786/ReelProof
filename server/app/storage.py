from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from genblaze_core import KeyStrategy, ObjectLockConfig, ObjectStorageSink, ParquetSink
from genblaze_s3 import S3StorageBackend

from .config import settings


@lru_cache(maxsize=1)
def get_backend() -> S3StorageBackend:
    """Cached B2 backend — constructed once, reused across requests."""
    return S3StorageBackend.for_backblaze(
        settings.b2_bucket,
        region=settings.b2_region,
        key_id=settings.b2_key_id or None,
        app_key=settings.b2_app_key or None,
        public_url_base=settings.b2_public_url_base or None,
        auto_lifecycle=True,
    )


def build_sink() -> ObjectStorageSink:
    """New sink per run — ObjectStorageSink is not reentrant across runs."""
    os.makedirs(settings.data_dir, exist_ok=True)

    lock_config = None
    if settings.b2_key_id:  # only apply lock when B2 is actually configured
        lock_config = ObjectLockConfig(
            retain_until=datetime.now(timezone.utc) + timedelta(days=365),
            mode="GOVERNANCE",
        )

    return ObjectStorageSink(
        get_backend(),
        prefix="reelproof",
        key_strategy=KeyStrategy.HIERARCHICAL,
        parquet_sink=ParquetSink(settings.data_dir),
        manifest_lock=lock_config,
    )


def verify_run(run_id: str) -> dict:
    """Fetch manifest from B2 and verify integrity. Returns a summary dict."""
    backend = get_backend()
    sink = build_sink()

    try:
        manifest = sink.read_manifest_by_run_id(run_id, verify=True)
    except Exception as exc:
        return {"run_id": run_id, "verified": False, "error": str(exc)}

    steps = manifest.run.steps if manifest.run else []
    provider = steps[0].provider if steps else None
    model = steps[0].model if steps else None

    return {
        "run_id": run_id,
        "verified": manifest.verify(),
        "manifest_hash": manifest.canonical_hash,
        "provider": provider,
        "model": model,
        "created_at": manifest.run.started_at.isoformat() if manifest.run and manifest.run.started_at else None,
        "parent_run_id": manifest.run.parent_run_id if manifest.run else None,
    }
