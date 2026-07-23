from __future__ import annotations

from genblaze_core import Evaluator, EvaluationResult
from genblaze_openai import chat

from ..config import settings

_JUDGE_SYSTEM = """\
You are a strict quality judge for short-form social video frames.
Score the provided image on a scale of 0.0 to 1.0 across four dimensions,
then return ONLY valid JSON:

{
  "hook_strength": 0.0-1.0,     // does the visual grab attention instantly?
  "text_legibility": 0.0-1.0,   // is any on-screen text crisp and readable?
  "visual_artifacts": 0.0-1.0,  // 1.0 = clean, 0.0 = heavy AI artifacts/glitches
  "on_brand": 0.0-1.0,          // cohesive aesthetic, not random/clashing
  "overall": 0.0-1.0,           // your holistic score
  "feedback": "<one sentence: what specifically to improve, or null if passing>"
}

Be strict. A score >= 0.7 overall is passing. Flag garbled text, uncanny faces,
bad composition, or inconsistent style aggressively.
"""


class VisionJudge(Evaluator):
    """Vision-model quality judge. Uses gpt-4o-mini (cheaper, faster) — different from the generator."""

    def evaluate(self, result) -> EvaluationResult:
        import json

        steps = result.run.steps
        if not steps or not steps[-1].assets:
            return EvaluationResult(passed=False, score=0.0, feedback="No asset produced")

        url = steps[-1].assets[0].url

        resp = chat(
            "gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Score this image:"},
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                }
            ],
            system=_JUDGE_SYSTEM,
            api_key=settings.openai_api_key or None,
        )

        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip().rstrip("`").strip()

        try:
            scores = json.loads(raw)
        except Exception:
            return EvaluationResult(passed=False, score=0.0, feedback="Judge parse error")

        overall = float(scores.get("overall", 0.0))
        feedback = scores.get("feedback") or None
        passed = overall >= settings.judge_pass_threshold

        return EvaluationResult(passed=passed, score=overall, feedback=feedback)
