from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from genblaze_core import Asset, Pipeline

from ..config import settings
from ..schemas import BeatPlan, BeatResult, CampaignResult, JobStatus, RenderMode
from ..storage import build_sink
from .assemble import assemble_slideshow
from .audio import generate_music
from .captions import burn_caption
from .loop import run_beat_loop
from .planner import plan_beats


def run_campaign(
    job_id: str,
    topic: str,
    mode: RenderMode,
    beat_count: int,
    emit: Callable[[str, dict[str, Any]], None],  # emit(event_type, data)
    product_assets: Sequence[Asset] | None = None,
    record_provenance: Callable[[dict[str, Any]], None] | None = None,
) -> CampaignResult:
    """
    Full synchronous engine. Called from a background thread.
    `emit` sends progress events to the SSE queue.
    """
    emit("engine.started", {"job_id": job_id, "topic": topic, "mode": mode.value})

    try:
        if mode is not RenderMode.slideshow:
            raise ValueError("POV montage is planned for Phase 6; use slideshow mode for now")

        # A unique work directory prevents simultaneous jobs from overwriting
        # each other's captioned frames and assembled reel.
        work_dir = settings.output_path / job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # Fail before paid provider calls if B2 is unavailable.
        sink = build_sink()

        # 1. Plan
        emit("step.started", {"step": "planner", "message": "Planning beats..."})
        product_context = (
            "Use the uploaded product as the visual anchor." if product_assets else None
        )
        beat_plan: BeatPlan = plan_beats(topic, beat_count, product_context=product_context)
        emit("step.completed", {"step": "planner", "hook": beat_plan.hook, "beats": beat_count})

        beat_results: list[BeatResult] = []
        captioned_paths: list[str] = []
        total_agent_cost = 0.0

        # 2. Per-beat: generate -> vision judge -> refine (bounded) -> caption.
        for beat in beat_plan.beats:
            emit("beat.started", {"beat_index": beat.index, "concept": beat.concept})

            def record_iteration(record: dict[str, Any], beat_index: int = beat.index) -> None:
                if record_provenance:
                    record_provenance(record)
                emit(
                    "beat.judged",
                    {
                        "beat_index": beat_index,
                        "iteration": record["iteration"],
                        "score": record["score"],
                        "passed": record["passed"],
                        "feedback": record["feedback"],
                        "run_id": record["run_id"],
                    },
                )

            loop_result = run_beat_loop(
                beat,
                sink=sink,
                product_assets=product_assets,
                on_iteration=record_iteration,
            )
            total_agent_cost += loop_result.total_cost_usd
            url = loop_result.asset_url
            emit(
                "beat.generated",
                {
                    "beat_index": beat.index,
                    "image_url": url,
                    "iterations": loop_result.iterations,
                    "passed": loop_result.passed,
                },
            )

            # Burn caption
            captioned_path = burn_caption(url, beat.caption, beat.index, output_dir=work_dir)
            captioned_paths.append(captioned_path)

            beat_results.append(
                BeatResult(
                    index=beat.index,
                    image_url=url,
                    # Captioned frames are local assembly intermediates in Phase 2.
                    # Phase 3 will persist them and expose durable asset URLs.
                    captioned_url=None,
                    judge_score=loop_result.score,
                    judge_iterations=loop_result.iterations,
                    passed=loop_result.passed,
                )
            )
            emit("beat.completed", {"beat_index": beat.index})

        # 3. Music
        emit("step.started", {"step": "audio", "message": "Generating music..."})
        total_dur = len(beat_plan.beats) * settings.slideshow_beat_duration_sec
        music_url = generate_music(topic, duration_sec=total_dur)
        emit("step.completed", {"step": "audio"})

        # 4. Assemble
        emit("step.started", {"step": "assemble", "message": "Assembling slideshow..."})
        reel_path = assemble_slideshow(
            captioned_paths,
            music_url,
            settings.slideshow_beat_duration_sec,
            output_dir=work_dir,
        )
        emit("step.completed", {"step": "assemble", "path": reel_path})

        # 5. Store in B2
        emit("step.started", {"step": "storage", "message": "Uploading to B2..."})
        reel_asset = Asset(
            url=Path(reel_path).resolve().as_uri(),
            media_type="video/mp4",
        )
        store_result = Pipeline.ingest(
            assets=[reel_asset],
            source="reelproof-assembly",
            source_metadata={"topic": topic, "mode": mode.value, "job_id": job_id},
            sink=sink,
            name=f"reel-store-{job_id}",
        )
        reel_b2_url = store_result.run.steps[0].assets[0].url
        manifest_hash = store_result.manifest.canonical_hash
        run_id = store_result.run.run_id
        verified = store_result.manifest.verify()
        if not verified:
            raise RuntimeError("Final campaign manifest failed verification")
        if record_provenance:
            record_provenance(
                {
                    "run_id": run_id,
                    "manifest_json": store_result.manifest.model_dump_json(),
                    "manifest_hash": manifest_hash,
                    "manifest_uri": store_result.manifest.manifest_uri,
                    "parent_run_id": store_result.run.parent_run_id,
                }
            )
        emit("step.completed", {"step": "storage", "verified": verified, "run_id": run_id})

        emit("engine.completed", {"job_id": job_id, "run_id": run_id, "verified": verified})

        return CampaignResult(
            job_id=job_id,
            topic=topic,
            mode=mode,
            status=JobStatus.done,
            beat_plan=beat_plan,
            beats=beat_results,
            reel_url=reel_b2_url,
            suggested_caption=beat_plan.suggested_caption,
            hashtags=beat_plan.hashtags,
            manifest_hash=manifest_hash,
            manifest_uri=store_result.manifest.manifest_uri,
            run_id=run_id,
            total_cost_usd=total_agent_cost,
        )

    except Exception as exc:
        emit("engine.failed", {"job_id": job_id, "error": str(exc)})
        return CampaignResult(
            job_id=job_id,
            topic=topic,
            mode=mode,
            status=JobStatus.failed,
            error=str(exc),
        )
