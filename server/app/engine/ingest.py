from __future__ import annotations

from pathlib import Path

from genblaze_core import Asset, Pipeline

from ..storage import build_sink
from .safety import ensure_assets_allowed


def ingest_product_image(
    *,
    local_path: Path,
    filename: str,
    media_type: str,
    job_id: str,
) -> dict[str, str | None]:
    """Store one creator-uploaded image in B2 with a GenBlaze manifest."""
    if not local_path.is_file():
        raise FileNotFoundError(f"Upload staging file does not exist: {local_path}")

    upload_asset = Asset(url=local_path.resolve().as_uri(), media_type=media_type)
    ensure_assets_allowed([upload_asset])

    result = Pipeline.ingest(
        assets=[upload_asset],
        source="reelproof-product-upload",
        source_metadata={"job_id": job_id, "filename": filename},
        sink=build_sink(),
        name=f"product-upload-{job_id}",
    )
    assets = result.run.steps[0].assets
    if not assets:
        raise RuntimeError("Product upload ingestion completed without an asset")

    asset = assets[0]
    manifest = result.manifest
    if not manifest.verify():
        raise RuntimeError("Product upload manifest failed verification")

    return {
        "asset_id": asset.asset_id,
        "asset_url": asset.url,
        "sha256": asset.sha256,
        "run_id": result.run.run_id,
        "manifest_hash": manifest.canonical_hash,
        "manifest_uri": manifest.manifest_uri,
        "manifest_json": manifest.model_dump_json(),
        "parent_run_id": result.run.parent_run_id,
    }
