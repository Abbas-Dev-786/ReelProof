from __future__ import annotations

import re
from urllib.parse import urlparse

from genblaze_core import Asset, ModerationHook, ModerationResult
from genblaze_core.providers import RetryPolicy


class ContentSafetyError(ValueError):
    """Raised before an unsafe asset or prompt enters a provider workflow."""


class ReelProofModerationHook(ModerationHook):
    """Local baseline moderation for every GenBlaze media pipeline.

    The hook blocks a narrow set of unambiguous high-risk requests and rejects
    malformed output assets before they are cached or persisted. It is designed
    as a deterministic baseline; deployments can replace it with a provider
    backed image moderation implementation without changing pipeline wiring.
    """

    _blocked_patterns = (
        ("child sexual exploitation", re.compile(r"\b(?:child|minor|underage).{0,80}\b(?:sexual|nude|explicit)\b", re.I)),
        ("graphic violence", re.compile(r"\b(?:graphic gore|dismemberment|torture)\b", re.I)),
        ("hate or extremist propaganda", re.compile(r"\b(?:nazi propaganda|racial slur|ethnic cleansing)\b", re.I)),
    )
    _allowed_media_types = frozenset(
        {
            "image/jpeg",
            "image/png",
            "image/webp",
            "video/mp4",
            "audio/mpeg",
            "audio/mp4",
            "audio/wav",
        }
    )
    _allowed_schemes = frozenset({"file", "http", "https"})

    def check_prompt(self, prompt: str | None, params: dict[str, object]) -> ModerationResult:
        del params
        normalized = " ".join((prompt or "").split())
        for category, pattern in self._blocked_patterns:
            if pattern.search(normalized):
                return ModerationResult(
                    allowed=False,
                    reason="The request violates ReelProof content safety rules.",
                    flagged_categories=[category],
                )
        return ModerationResult(allowed=True)

    def check_output(self, assets: list[Asset]) -> ModerationResult:
        if not assets:
            return ModerationResult(
                allowed=False,
                reason="Generation returned no assets.",
                flagged_categories=["empty_output"],
            )
        for asset in assets:
            if asset.media_type not in self._allowed_media_types:
                return ModerationResult(
                    allowed=False,
                    reason="Generation returned an unsupported media type.",
                    flagged_categories=["unsupported_media_type"],
                )
            if urlparse(str(asset.url)).scheme not in self._allowed_schemes:
                return ModerationResult(
                    allowed=False,
                    reason="Generation returned an unsafe asset URL.",
                    flagged_categories=["unsafe_asset_url"],
                )
        return ModerationResult(allowed=True)


def moderation_hook() -> ReelProofModerationHook:
    """Create a hook per pipeline so future provider-backed state stays isolated."""
    return ReelProofModerationHook()


def ensure_prompt_allowed(prompt: str) -> None:
    result = moderation_hook().check_prompt(prompt, {})
    if not result.allowed:
        raise ContentSafetyError(result.reason or "The request was rejected by content safety.")


def ensure_assets_allowed(assets: list[Asset]) -> None:
    result = moderation_hook().check_output(assets)
    if not result.allowed:
        raise ContentSafetyError(result.reason or "The asset was rejected by content safety.")


def image_retry_policy() -> RetryPolicy:
    """Use bounded retries for inexpensive still-image requests."""
    return RetryPolicy.aggressive()


def audio_retry_policy() -> RetryPolicy:
    """Avoid repeated long audio submissions while still recovering transient polls."""
    return RetryPolicy.conservative()


def video_retry_policy() -> RetryPolicy:
    """Use the SDK's conservative policy for billed, long-running video work."""
    return RetryPolicy.conservative()
