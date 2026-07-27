"""Lifecycle-managed local workspaces for media sent to object storage."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _system_temp_directory() -> Path:
    """Return the resolved OS temporary directory used by GenBlaze transfers."""
    return Path(tempfile.gettempdir()).resolve()


def require_media_workspace(path: str | Path) -> Path:
    """Validate and create a workspace accepted by GenBlaze local-file transfer.

    GenBlaze deliberately restricts ``file://`` uploads to the operating
    system's temporary directory unless its sink is explicitly configured
    otherwise. The production sink does not expose that configuration, so
    every transient media artifact must stay within this directory.
    """
    workspace = Path(path).resolve()
    temporary_root = _system_temp_directory()
    if not workspace.is_relative_to(temporary_root):
        raise ValueError(
            "Media workspace must be inside the system temporary directory "
            f"({temporary_root}); got {workspace}"
        )
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@contextmanager
def media_workspace() -> Iterator[Path]:
    """Yield an isolated temporary workspace and remove it when the job ends."""
    with tempfile.TemporaryDirectory(prefix="reelproof-media-") as directory:
        yield require_media_workspace(directory)
