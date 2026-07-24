from __future__ import annotations

from genblaze_core import Modality, Pipeline
from genblaze_stability_audio import StabilityAudioProvider

from ..config import settings
from .safety import audio_retry_policy, moderation_hook


def generate_music(topic: str, duration_sec: float = 20.0) -> str:
    """Generate background music for the reel. Returns asset URL."""
    if not settings.stability_api_key:
        raise RuntimeError("STABILITY_API_KEY is required to generate slideshow music")
    if duration_sec <= 0:
        raise ValueError("duration_sec must be greater than zero")

    settings.output_path.mkdir(parents=True, exist_ok=True)

    provider = StabilityAudioProvider(
        api_key=settings.stability_api_key or None, retry_policy=audio_retry_policy()
    )

    result = (
        Pipeline("reel-music", moderation=moderation_hook())
        .step(
            provider,
            model="stable-audio-2.5",
            prompt=f"upbeat background music for a short-form social video about: {topic}. No vocals.",
            modality=Modality.AUDIO,
            duration=duration_sec,
        )
        .run(timeout=180, max_retries=settings.audio_step_retries)
    )

    steps = result.run.steps
    if not steps or not steps[0].assets:
        raise RuntimeError("Music generation returned no assets")

    return str(steps[0].assets[0].url)
