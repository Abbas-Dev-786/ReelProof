from __future__ import annotations

import json
from typing import Any, cast

from genblaze_core import EvaluationResult, Evaluator
from genblaze_nvidia import chat
from pydantic import BaseModel, ConfigDict, Field

from ..config import settings
from ..observability import finish_trace, trace_operation

_JUDGE_SYSTEM = """\
You are a strict quality judge for short-form social video frames.
Score the provided image on a scale of 0.0 to 1.0 across four dimensions,
then return ONLY valid JSON:

{
  "hook_strength": 0.0-1.0,     // does the visual grab attention instantly?
  "text_legibility": 0.0-1.0,   // is the lower caption safe-zone clean and high contrast?
  "visual_artifacts": 0.0-1.0,  // 1.0 = clean, 0.0 = heavy AI artifacts/glitches
  "on_brand": 0.0-1.0,          // cohesive aesthetic, not random/clashing
  "overall": 0.0-1.0,           // your holistic score
  "feedback": "<one sentence: what specifically to improve, or null if passing>"
}

Be strict. A score >= 0.7 overall is passing. Flag garbled text, uncanny faces,
bad composition, or inconsistent style aggressively.
"""


class JudgeScoresResponse(BaseModel):
    """JSON schema sent to the VLM; parsing below remains the trust boundary."""

    model_config = ConfigDict(extra="forbid")

    hook_strength: float = Field(ge=0, le=1)
    text_legibility: float = Field(ge=0, le=1)
    visual_artifacts: float = Field(ge=0, le=1)
    on_brand: float = Field(ge=0, le=1)
    overall: float = Field(ge=0, le=1)
    feedback: str | None = None


class VisionJudge(Evaluator):
    """Vision quality judge backed by Qwen's flagship hosted NVIDIA NIM VLM."""

    def evaluate(self, result) -> EvaluationResult:
        if not settings.nvidia_api_key:
            raise RuntimeError("NVIDIA_API_KEY is required for the Phase 4 vision judge")

        steps = result.run.steps
        image_asset = next(
            (
                asset
                for step in reversed(steps)
                for asset in step.assets
                if str(getattr(asset, "media_type", "image/")).startswith("image/")
            ),
            None,
        )
        if image_asset is None:
            return EvaluationResult(passed=False, score=0.0, feedback="No asset produced")

        url = image_asset.url

        with trace_operation(
            "reelproof.vision-judge",
            inputs={"image_url": str(url)},
            metadata={"model": settings.nvidia_vision_model},
            run_type="llm",
        ) as trace:
            resp = chat(
                settings.nvidia_vision_model,
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
                temperature=0.1,
                response_format=JudgeScoresResponse,
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_chat_base_url or None,
            )
            finish_trace(trace, {"model": settings.nvidia_vision_model, "response_chars": len(resp.text)})

        try:
            scores = parse_judge_scores(resp.text)
        except Exception:
            return EvaluationResult(passed=False, score=0.0, feedback="Judge parse error")

        overall = cast(float, scores["overall"])
        feedback_value = scores.get("feedback")
        feedback = feedback_value if isinstance(feedback_value, str) else None
        passed = overall >= settings.judge_pass_threshold

        return EvaluationResult(passed=passed, score=overall, feedback=feedback, metadata=scores)


def parse_judge_scores(raw: str) -> dict[str, float | str | None]:
    """Parse and constrain the judge response before it influences a retry."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", maxsplit=2)[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    data: dict[str, Any] = json.loads(raw.strip().rstrip("`").strip())

    required = ("hook_strength", "text_legibility", "visual_artifacts", "on_brand", "overall")
    scores: dict[str, float | str | None] = {}
    for key in required:
        value = float(data[key])
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{key} must be between 0 and 1")
        scores[key] = value
    feedback = data.get("feedback")
    if feedback is not None and not isinstance(feedback, str):
        raise ValueError("feedback must be a string or null")
    scores["feedback"] = feedback
    return scores
