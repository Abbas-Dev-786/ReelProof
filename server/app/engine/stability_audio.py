"""Compatibility wrapper for Stable Audio's multipart-only API endpoint.

``genblaze-stability-audio==0.3.1`` passes its text-to-audio fields through
``httpx.Client.post(data=...)``. That serializes them as
``application/x-www-form-urlencoded``, but Stability's endpoint only accepts
``multipart/form-data``. Keep the upstream provider's generation and
provenance behavior while adapting that one outbound request shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import httpx
from genblaze_stability_audio import StabilityAudioProvider as _StabilityAudioProvider


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
