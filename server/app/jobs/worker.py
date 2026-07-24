from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any

from genblaze_core import Asset

from ..config import settings
from ..engine.run_engine import run_campaign
from ..schemas import RenderMode
from .store import append_event, record_provenance, renew_job_lease, set_failed, set_result

logger = logging.getLogger(__name__)
WORKER_ID = f"{os.uname().nodename}:{os.getpid()}:{uuid.uuid4()}"


class WorkerLeaseLost(RuntimeError):
    """Raised when a worker no longer owns the job it is attempting to finish."""


def _renew_lease_until_stopped(
    job_id: str, stop: threading.Event, lease_lost: threading.Event
) -> None:
    """Keep a long render owned by this worker until it reaches a terminal state."""
    interval = max(1, settings.job_lease_seconds // 3)
    while not stop.wait(interval):
        if not renew_job_lease(job_id, WORKER_ID, settings.job_lease_seconds):
            logger.warning("Lost campaign worker lease", extra={"job_id": job_id})
            lease_lost.set()
            return


def launch_worker(
    job_id: str,
    topic: str,
    mode: RenderMode,
    beat_count: int,
    product_assets: list[Asset] | None = None,
) -> None:
    """Spawn a leased worker; all progress is persisted for SSE replay."""

    def run() -> None:
        def emit(event_type: str, data: dict[str, Any]) -> None:
            if lease_lost.is_set() or not renew_job_lease(
                job_id, WORKER_ID, settings.job_lease_seconds
            ):
                lease_lost.set()
                raise WorkerLeaseLost(f"Worker lease lost for campaign {job_id}")
            append_event(job_id, event_type, data)

        def persist_provenance(record: dict[str, Any]) -> None:
            record_provenance(
                job_id=job_id,
                run_id=record["run_id"],
                manifest_json=record["manifest_json"],
                manifest_hash=record["manifest_hash"],
                manifest_uri=record["manifest_uri"],
                parent_run_id=record["parent_run_id"],
            )

        stop_heartbeat = threading.Event()
        lease_lost = threading.Event()
        heartbeat = threading.Thread(
            target=_renew_lease_until_stopped,
            args=(job_id, stop_heartbeat, lease_lost),
            daemon=True,
            name=f"lease-{job_id}",
        )
        heartbeat.start()
        try:
            result = run_campaign(
                job_id,
                topic,
                mode,
                beat_count,
                emit,
                product_assets=product_assets,
                record_provenance=persist_provenance,
            )
            if result.status.value == "done":
                set_result(job_id, result.model_dump_json(), worker_id=WORKER_ID)
            else:
                set_failed(job_id, result.error or "Campaign failed", worker_id=WORKER_ID)
        except Exception:
            logger.exception("Campaign worker crashed", extra={"job_id": job_id})
            set_failed(
                job_id,
                "Campaign worker crashed. Check server logs for details.",
                worker_id=WORKER_ID,
            )
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=1)

    t = threading.Thread(target=run, daemon=True, name=f"worker-{job_id}")
    t.start()
