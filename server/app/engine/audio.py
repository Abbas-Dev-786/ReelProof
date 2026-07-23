from __future__ import annotations

import os

from genblaze_core import Modality, Pipeline
from genblaze_stability_audio import StabilityAudioProvider

from ..config import settings


def generate_music(topic: str, duration_sec: float = 20.0) -> str:
    """Generate background music for the reel. Returns asset URL."""
    os.makedirs(settings.output_dir, exist_ok=True)

    provider = StabilityAudioProvider(api_key=settings.stability_api_key or None)

    result = (
        Pipeline("reel-music")
        .step(
            provider,
            model="stable-audio-2.5",
            prompt=f"upbeat background music for a short-form social video about: {topic}. No vocals.",
            modality=Modality.AUDIO,
            duration=duration_sec,
        )
        .run(timeout=180)
    )

    steps = result.run.steps
    if not steps or not steps[0].assets:
        raise RuntimeError("Music generation returned no assets")

    return steps[0].assets[0].url
