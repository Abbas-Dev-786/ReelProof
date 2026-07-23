from __future__ import annotations

import json

from genblaze_openai import chat

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


def plan_beats(topic: str, beat_count: int = 5, product_context: str | None = None) -> BeatPlan:
    user_msg = f"Topic: {topic}\nbeat_count: {beat_count}"
    if product_context:
        user_msg += f"\nProduct context: {product_context}"

    resp = chat(
        "gpt-4o",
        system=_SYSTEM,
        prompt=user_msg,
        temperature=0.8,
        api_key=settings.openai_api_key or None,
    )

    raw = resp.text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("`").strip()

    data = json.loads(raw)
    beats = [Beat(**b) for b in data["beats"]]
    return BeatPlan(
        hook=data["hook"],
        beats=beats,
        suggested_caption=data["suggested_caption"],
        hashtags=data.get("hashtags", []),
    )
