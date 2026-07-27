"""Optional, fail-open LangSmith instrumentation for ReelProof workflows."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)


def langsmith_tracer():
    """Create a GenBlaze tracer when LangSmith has been explicitly enabled.

    A fresh tracer is intentionally created per pipeline. GenBlaze tracers keep
    in-flight run state, so this prevents concurrent campaign workers from
    crossing parent or step identifiers.
    """
    if not settings.langsmith_tracing:
        return None
    if not settings.langsmith_api_key:
        logger.warning("LANGSMITH_TRACING is enabled but LANGSMITH_API_KEY is not configured")
        return None

    try:
        from genblaze_langsmith import LangSmithTracer
    except ImportError:
        logger.warning("LangSmith tracing is enabled but genblaze-langsmith is unavailable")
        return None

    try:
        return LangSmithTracer(
            project_name=settings.langsmith_project,
            api_key=settings.langsmith_api_key,
        )
    except Exception as exc:  # Observability must not interrupt a campaign.
        logger.warning("LangSmith tracer initialization failed: %s", exc)
        return None


@contextmanager
def trace_operation(
    name: str,
    *,
    inputs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    run_type: str = "chain",
) -> Iterator[Any | None]:
    """Add a LangSmith span around non-GenBlaze work without changing behavior."""
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        yield None
        return

    try:
        from langsmith import Client, trace
    except ImportError:
        logger.warning("LangSmith tracing is enabled but the langsmith package is unavailable")
        yield None
        return

    try:
        client = Client(
            api_key=settings.langsmith_api_key,
            workspace_id=settings.langsmith_workspace_id or None,
        )
        context = trace(
            name,
            run_type=run_type,
            inputs=inputs,
            metadata=metadata,
            project_name=settings.langsmith_project,
            tags=["reelproof"],
            client=client,
        )
        run = context.__enter__()
    except Exception as exc:  # Observability must not interrupt a campaign.
        logger.warning("LangSmith trace initialization failed: %s", exc)
        yield None
        return

    try:
        yield run
    except BaseException:
        try:
            context.__exit__(*sys.exc_info())
        except Exception as exc:  # Observability must not mask the original error.
            logger.warning("LangSmith trace finalization failed: %s", exc)
        raise
    else:
        try:
            context.__exit__(None, None, None)
        except Exception as exc:  # Observability must not interrupt a campaign.
            logger.warning("LangSmith trace finalization failed: %s", exc)


def finish_trace(run: Any | None, outputs: dict[str, Any]) -> None:
    """Attach safe, compact outputs to an optional manually-created span."""
    if run is not None:
        run.end(outputs=outputs)


def ingest_with_trace(
    *,
    assets: Sequence[Any],
    source: str,
    source_metadata: dict[str, Any] | None,
    sink: Any,
    name: str,
) -> Any:
    """Trace a GenBlaze ingest operation, whose convenience API has no tracer arg."""
    from genblaze_core import Pipeline

    with trace_operation(
        "reelproof.ingest",
        inputs={"source": source, "asset_urls": [str(asset.url) for asset in assets]},
        metadata={"pipeline_name": name, **(source_metadata or {})},
        run_type="tool",
    ) as trace:
        result = Pipeline.ingest(
            assets=assets,
            source=source,
            source_metadata=source_metadata,
            sink=sink,
            name=name,
        )
        finish_trace(
            trace,
            {
                "run_id": result.run.run_id,
                "manifest_hash": result.manifest.canonical_hash,
                "verified": result.manifest.verify(),
            },
        )
        return result
