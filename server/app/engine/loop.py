from __future__ import annotations

from genblaze_core import AgentContext, AgentLoop, Modality, Pipeline
from genblaze_gmicloud import GMICloudImageProvider

from ..config import settings
from ..schemas import Beat
from .judge import VisionJudge


def _image_provider() -> GMICloudImageProvider:
    return GMICloudImageProvider(api_key=settings.gmi_api_key or None)


def run_beat_loop(beat: Beat, style_suffix: str = "") -> tuple[str, float, int]:
    """
    Run the AgentLoop for one beat.
    Returns (winning_asset_url, final_score, iterations_used).
    """

    def build_pipeline(ctx: AgentContext) -> Pipeline:
        prompt = beat.concept
        if style_suffix:
            prompt = f"{prompt}. {style_suffix}"
        if ctx.last_evaluation and ctx.last_evaluation.feedback:
            prompt = f"{prompt} — {ctx.last_evaluation.feedback}"

        return Pipeline(f"beat-{beat.index}-iter-{ctx.iteration}").step(
            _image_provider(),
            model="reve-create",
            prompt=prompt,
            modality=Modality.IMAGE,
            fallback_models=["gemini-2.5-flash-image"],
        )

    loop = AgentLoop(
        build_pipeline,
        VisionJudge(),
        max_iterations=settings.max_agent_iterations,
    )

    agent_result = loop.run()

    # Best result = last iteration that ran (passed or hit cap)
    last_iter = agent_result.iterations[-1]
    steps = last_iter.result.run.steps
    if not steps or not steps[0].assets:
        raise RuntimeError(f"Beat {beat.index}: agent loop produced no assets")

    url = steps[0].assets[0].url
    score = last_iter.evaluation.score if last_iter.evaluation else 0.0
    iters = len(agent_result.iterations)

    return url, score, iters
