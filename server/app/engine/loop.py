from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from genblaze_core import AgentContext, AgentLoop, Asset, Modality, ObjectStorageSink, Pipeline
from genblaze_core.providers import per_unit
from genblaze_gmicloud import GMICloudImageProvider

from ..config import settings
from ..schemas import Beat
from .judge import VisionJudge


@dataclass(frozen=True)
class BeatLoopResult:
    asset_url: str
    score: float | None
    iterations: int
    passed: bool
    total_cost_usd: float


def _image_provider() -> GMICloudImageProvider:
    provider = GMICloudImageProvider(api_key=settings.gmi_api_key or None)
    provider.models.register_pricing(
        settings.gmi_image_model, per_unit(settings.gmi_image_unit_cost_usd)
    )
    provider.models.register_pricing(
        settings.gmi_product_image_model,
        per_unit(settings.gmi_product_image_unit_cost_usd),
    )
    return provider


def refine_prompt(concept: str, feedback: str | None, style_suffix: str = "") -> str:
    """Keep retry prompts deterministic and make the evaluator feedback visible."""
    parts = [concept]
    if style_suffix:
        parts.append(style_suffix)
    if feedback:
        parts.append(feedback)
    return " — ".join(parts)


def run_beat_loop(
    beat: Beat,
    *,
    sink: ObjectStorageSink,
    product_assets: Sequence[Asset] | None = None,
    style_suffix: str = "",
    on_iteration: Callable[[dict[str, Any]], None] | None = None,
) -> BeatLoopResult:
    """
    Run the AgentLoop for one beat.
    Stores every attempt through ``sink`` so AgentLoop's automatic
    parent_run_id links are available to the provenance API.
    """
    if not settings.gmi_api_key:
        raise RuntimeError("GMI_API_KEY is required to run the self-healing image loop")

    product_input = list(product_assets or [])[:1]

    def build_pipeline(ctx: AgentContext) -> Pipeline:
        prompt = refine_prompt(
            beat.concept,
            ctx.last_evaluation.feedback if ctx.last_evaluation else None,
            style_suffix,
        )

        return Pipeline(f"beat-{beat.index}-iter-{ctx.iteration}").step(
            _image_provider(),
            model=settings.gmi_product_image_model if product_input else settings.gmi_image_model,
            prompt=prompt,
            modality=Modality.IMAGE,
            aspect_ratio="9:16",
            external_inputs=product_input or None,
            fallback_models=["gemini-2.5-flash-image"],
        )

    loop = AgentLoop(
        build_pipeline,
        VisionJudge(),
        max_iterations=settings.max_agent_iterations,
    )

    agent_result = loop.run(sink=sink, timeout=120)

    # The last result is either a pass or the best available bounded attempt.
    last_iter = agent_result.iterations[-1]
    steps = last_iter.result.run.steps
    if not steps or not steps[0].assets:
        raise RuntimeError(f"Beat {beat.index}: agent loop produced no assets")

    if on_iteration:
        for iteration in agent_result.iterations:
            evaluation = iteration.evaluation
            on_iteration(
                {
                    "beat_index": beat.index,
                    "iteration": iteration.index,
                    "run_id": iteration.result.run.run_id,
                    "manifest_json": iteration.result.manifest.model_dump_json(),
                    "manifest_hash": iteration.result.manifest.canonical_hash,
                    "manifest_uri": iteration.result.manifest.manifest_uri,
                    "parent_run_id": iteration.result.run.parent_run_id,
                    "score": evaluation.score,
                    "passed": evaluation.passed,
                    "feedback": evaluation.feedback,
                }
            )

    return BeatLoopResult(
        asset_url=steps[0].assets[0].url,
        score=last_iter.evaluation.score,
        iterations=len(agent_result.iterations),
        passed=agent_result.passed,
        total_cost_usd=agent_result.total_cost_usd,
    )
