from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from ..engine.run_engine import run_campaign
from ..schemas import RenderMode
from .store import save_checkpoint, set_failed, set_result, set_running

# Per-job asyncio queues for SSE relay
_queues: dict[str, asyncio.Queue] = {}
_queues_lock = threading.Lock()


def get_queue(job_id: str) -> asyncio.Queue:
    with _queues_lock:
        if job_id not in _queues:
            _queues[job_id] = asyncio.Queue()
        return _queues[job_id]


def drop_queue(job_id: str) -> None:
    with _queues_lock:
        _queues.pop(job_id, None)


def _put_event(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, event_type: str, data: dict) -> None:
    """Thread-safe put into the asyncio queue from the worker thread."""
    payload = {"type": event_type, **data}
    asyncio.run_coroutine_threadsafe(queue.put(payload), loop)


def launch_worker(
    job_id: str,
    topic: str,
    mode: RenderMode,
    beat_count: int,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Spawn a daemon thread that runs the engine and feeds the SSE queue."""
    queue = get_queue(job_id)

    def run() -> None:
        set_running(job_id)

        def emit(event_type: str, data: dict) -> None:
            _put_event(loop, queue, event_type, data)

        result = run_campaign(job_id, topic, mode, beat_count, emit)

        if result.status.value == "done":
            set_result(job_id, result.model_dump_json())
        else:
            set_failed(job_id, result.error or "unknown error")

        # Sentinel: tell the SSE generator to close
        asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    t = threading.Thread(target=run, daemon=True, name=f"worker-{job_id}")
    t.start()
