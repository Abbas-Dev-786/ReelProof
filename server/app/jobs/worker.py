from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any

from genblaze_core import Asset

from ..engine.run_engine import run_campaign
from ..schemas import RenderMode
from .store import record_provenance, set_failed, set_result

# Per-job asyncio queues for SSE relay
_queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}
_queues_lock = threading.Lock()
logger = logging.getLogger(__name__)


def get_queue(job_id: str) -> asyncio.Queue[dict[str, Any] | None]:
    with _queues_lock:
        if job_id not in _queues:
            _queues[job_id] = asyncio.Queue()
        return _queues[job_id]


def drop_queue(job_id: str) -> None:
    with _queues_lock:
        _queues.pop(job_id, None)


def _put_event(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[dict[str, Any] | None],
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Thread-safe put into the asyncio queue from the worker thread."""
    payload = {"type": event_type, **data}
    future = asyncio.run_coroutine_threadsafe(queue.put(payload), loop)
    future.add_done_callback(_log_delivery_error)


def _log_delivery_error(future: Future[Any]) -> None:
    try:
        future.result()
    except Exception:
        logger.debug("Unable to deliver campaign stream event", exc_info=True)


def launch_worker(
    job_id: str,
    topic: str,
    mode: RenderMode,
    beat_count: int,
    loop: asyncio.AbstractEventLoop,
    product_assets: list[Asset] | None = None,
) -> None:
    """Spawn a daemon thread that runs the engine and feeds the SSE queue."""
    queue = get_queue(job_id)

    def run() -> None:
        def emit(event_type: str, data: dict[str, Any]) -> None:
            _put_event(loop, queue, event_type, data)

        def persist_provenance(record: dict[str, Any]) -> None:
            record_provenance(
                job_id=job_id,
                run_id=record["run_id"],
                manifest_json=record["manifest_json"],
                manifest_hash=record["manifest_hash"],
                manifest_uri=record["manifest_uri"],
                parent_run_id=record["parent_run_id"],
            )

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
                set_result(job_id, result.model_dump_json())
            else:
                set_failed(job_id, result.error or "Campaign failed")
        except Exception:
            logger.exception("Campaign worker crashed", extra={"job_id": job_id})
            set_failed(job_id, "Campaign worker crashed. Check server logs for details.")
        finally:
            # Sentinel: tell connected SSE generators that the engine has finished.
            terminal_event = asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            terminal_event.add_done_callback(_log_delivery_error)

    t = threading.Thread(target=run, daemon=True, name=f"worker-{job_id}")
    t.start()
