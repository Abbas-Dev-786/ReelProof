"""Compatibility wrapper for Stable Audio's multipart-only API endpoint.

``genblaze-stability-audio==0.3.1`` passes its text-to-audio fields through
``httpx.Client.post(data=...)``. That serializes them as
``application/x-www-form-urlencoded``, but Stability's endpoint only accepts
``multipart/form-data``. Keep the upstream provider's generation and
provenance behavior while adapting that one outbound request shape.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PureWindowsPath
from typing import Any, cast
from urllib.parse import unquote, urlparse

import httpx
from genblaze_stability_audio import StabilityAudioProvider as _StabilityAudioProvider

_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _normalize_generated_file_url(url: str) -> str:
    r"""Fix malformed Windows file URLs emitted by genblaze-stability-audio.

    Upstream builds URLs with ``file://{quote(str(path))}``. On Windows that
    turns ``C:\...`` into ``file://C%3A%5C...``. URL parsers treat the encoded
    drive/path as the URL host and leave ``path`` empty, so GenBlaze later
    resolves the local file as the process working directory.
    """
    parsed = urlparse(url)
    if parsed.scheme != "file" or not parsed.netloc or parsed.path not in {"", "/"}:
        return url

    decoded_netloc = unquote(parsed.netloc)
    if not _WINDOWS_ABSOLUTE_PATH_RE.match(decoded_netloc):
        return url

    return PureWindowsPath(decoded_netloc).as_uri()


class _MultipartFormDataClient:
    """Adapt the upstream provider's ``data=`` call to multipart fields."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def post(
        self,
        url: str,
        *,
        data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        if data is not None:
            # A ``(None, value)`` file tuple is how httpx encodes ordinary
            # multipart fields without assigning a filename to them.
            kwargs["files"] = [(str(name), (None, str(value))) for name, value in data.items()]
        return self._client.post(url, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class StabilityAudioProvider(_StabilityAudioProvider):
    """Stable Audio provider that submits text-to-audio fields as multipart."""

    def _get_http_client(self) -> _MultipartFormDataClient:
        if self._http_client is None:
            self._http_client = _MultipartFormDataClient(httpx.Client(timeout=self._http_timeout))
        return cast(_MultipartFormDataClient, self._http_client)

    def generate(self, step: Any, config: Any | None = None) -> Any:
        generated_step = super().generate(step, config=config)
        for asset in generated_step.assets:
            asset.url = _normalize_generated_file_url(asset.url)
        return generated_step
