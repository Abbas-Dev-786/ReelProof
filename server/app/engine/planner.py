from __future__ import annotations

import json

from genblaze_nvidia import chat

from ..config import settings
from ..schemas import Beat, BeatPlan

_SYSTEM = """\
You are a faceless short-form content strategist. Given a topic, produce a beat plan for a
9:16 vertical social video (TikTok/Reels style). Reply ONLY with valid JSON matching this schema:

{
  "hook": "<one-line attention-grabbing opener>",
  "beats": [
    {
      "index": 0,
      "concept": "<visual scene description for image generation>",
      "caption": "<short on-screen text, max 8 words>",
      "vo": "<optional voiceover line, or null>"
    }
  ],
  "suggested_caption": "<post caption with emojis>",
  "hashtags": ["tag1", "tag2"]
}

Rules:
- concept must describe a clean, photorealistic, faceless scene (no people's faces)
- caption must be legible on a dark background; use title case; max 8 words
- 3-8 beats depending on beat_count param
- hashtags: 5-10 relevant tags without the # symbol
"""


def parse_beat_plan(raw: str, beat_count: int) -> BeatPlan:
    """Validate the model response before it can enter the render pipeline."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", maxsplit=2)[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    raw = raw.strip().rstrip("`").strip()

    data = json.loads(raw)
    beats = [Beat(**beat) for beat in data["beats"]]
    if len(beats) != beat_count:
        raise ValueError(f"Planner returned {len(beats)} beats; expected exactly {beat_count}")

    expected_indexes = list(range(beat_count))
    actual_indexes = [beat.index for beat in beats]
    if actual_indexes != expected_indexes:
        raise ValueError(f"Planner beat indexes must be {expected_indexes}; got {actual_indexes}")

    return BeatPlan(
        hook=data["hook"],
        beats=beats,
        suggested_caption=data["suggested_caption"],
        hashtags=data.get("hashtags", []),
    )


def plan_beats(topic: str, beat_count: int = 5, product_context: str | None = None) -> BeatPlan:
    if not settings.nvidia_api_key:
        raise RuntimeError("NVIDIA_API_KEY is required to plan a campaign")

    user_msg = f"Topic: {topic}\nbeat_count: {beat_count}"
    if product_context:
        user_msg += f"\nProduct context: {product_context}"

    resp = chat(
        settings.nvidia_planner_model,
        system=_SYSTEM,
        prompt=user_msg,
        temperature=0.8,
        response_format=BeatPlan,
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_chat_base_url or None,
    )

    return parse_beat_plan(resp.text, beat_count)
