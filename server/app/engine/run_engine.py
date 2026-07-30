from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from genblaze_core import Asset

from ..config import settings
from ..jobs.store import complete_checkpoint, pending_checkpoints, save_checkpoint
from ..observability import finish_trace, ingest_with_trace, trace_operation
from ..schemas import Beat, BeatPlan, BeatResult, CampaignResult, JobStatus, RenderMode
from ..storage import build_sink, readable_asset_url
from ..workspace import media_workspace, require_media_workspace
from .assemble import assemble_pov_montage, assemble_slideshow
from .audio import GeneratedAudio, generate_music_asset, generate_voiceover_asset
from .beat_render import POVBeatRender, resume_pov_video, run_pov_beat_loop
from .captions import burn_caption, caption_renderer_error, render_title_card
from .loop import run_beat_loop
from .planner import plan_beats
from .safety import ensure_assets_allowed


def _store_final_reel(
    *,
    job_id: str,
    topic: str,
    mode: RenderMode,
    reel_path: str,
    sink: Any,
    record_provenance: Callable[[dict[str, Any]], None] | None,
) -> tuple[str, str, str | None, str, bool]:
    """Persist the assembled MP4 and its verified manifest in B2."""
    reel_asset = Asset(url=Path(reel_path).resolve().as_uri(), media_type="video/mp4")
    ensure_assets_allowed([reel_asset])
    store_result = ingest_with_trace(
        assets=[reel_asset],
        source="reelproof-assembly",
        source_metadata={"topic": topic, "mode": mode.value, "job_id": job_id},
        sink=sink,
        name=f"reel-store-{job_id}",
    )
    verified = store_result.manifest.verify()
    if not verified:
        raise RuntimeError("Final campaign manifest failed verification")
    if record_provenance:
        record_provenance(
            {
                "run_id": store_result.run.run_id,
                "manifest_json": store_result.manifest.model_dump_json(),
                "manifest_hash": store_result.manifest.canonical_hash,
                "manifest_uri": store_result.manifest.manifest_uri,
                "parent_run_id": store_result.run.parent_run_id,
            }
        )
    return (
        str(store_result.run.steps[0].assets[0].url),
        store_result.manifest.canonical_hash,
        store_result.manifest.manifest_uri,
        store_result.run.run_id,
        verified,
    )


def _store_local_intermediate(
    *,
    job_id: str,
    topic: str,
    mode: RenderMode,
    path: str,
    media_type: str,
    asset_kind: str,
    record_provenance: Callable[[dict[str, Any]], None] | None,
) -> str:
    """Persist a local assembly artifact and record its verified manifest.

    ffmpeg outputs are local by design, but they are still user-visible assets.
    Persisting them closes the provenance gap between provider outputs and the
    final reel without exposing temporary paths through the API.
    """
    asset = Asset(url=Path(path).resolve().as_uri(), media_type=media_type)
    ensure_assets_allowed([asset])
    result = ingest_with_trace(
        assets=[asset],
        source="reelproof-intermediate",
        source_metadata={
            "job_id": job_id,
            "topic": topic,
            "mode": mode.value,
            "asset_kind": asset_kind,
        },
        sink=build_sink(),
        name=f"reelproof-{asset_kind}-{job_id}",
    )
    if not result.manifest.verify():
        raise RuntimeError(f"{asset_kind} manifest failed verification")
    if record_provenance:
        record_provenance(
            {
                "run_id": result.run.run_id,
                "manifest_json": result.manifest.model_dump_json(),
                "manifest_hash": result.manifest.canonical_hash,
                "manifest_uri": result.manifest.manifest_uri,
                "parent_run_id": result.run.parent_run_id,
            }
        )
    return str(result.run.steps[0].assets[0].url)


def _record_generated_audio(
    audio: GeneratedAudio | None,
    record_provenance: Callable[[dict[str, Any]], None] | None,
) -> None:
    """Attach a durable audio pipeline's manifest to the campaign lineage."""
    if audio is None or not audio.run_id or not record_provenance:
        return
    record_provenance(
        {
            "run_id": audio.run_id,
            "manifest_json": audio.manifest_json or "{}",
            "manifest_hash": audio.manifest_hash or "",
            "manifest_uri": audio.manifest_uri,
            "parent_run_id": audio.parent_run_id,
        }
    )


async def _render_or_resume_pov_beat(
    *,
    job_id: str,
    beat: Any,
    sink: Any,
    product_assets: Sequence[Asset] | None,
    checkpoints: list[dict[str, Any]],
    emit: Callable[[str, dict[str, Any]], None],
    record_provenance: Callable[[dict[str, Any]], None] | None,
) -> POVBeatRender:
    """Resume an accepted video request when possible; otherwise render it once."""
    matching_checkpoint = next(
        (
            checkpoint
            for checkpoint in checkpoints
            if checkpoint["checkpoint"].get("kind") == "pov-video"
            and checkpoint["checkpoint"].get("beat_index") == beat.index
        ),
        None,
    )
    if matching_checkpoint is not None:
        emit("beat.resuming", {"beat_index": beat.index})
        rendered = await resume_pov_video(matching_checkpoint, sink=sink)
        complete_checkpoint(job_id, matching_checkpoint["step_id"])
        emit("beat.resumed", {"beat_index": beat.index, "video_url": rendered.video_url})
        return rendered

    checkpoint_step_ids: list[str] = []

    def checkpoint_video(step_id: str, prediction_id: Any, payload: dict[str, Any]) -> None:
        checkpoint_step_ids.append(step_id)
        save_checkpoint(job_id, step_id, prediction_id, payload)
        emit("beat.checkpointed", {"beat_index": beat.index, "step_id": step_id})

    def record_iteration(record: dict[str, Any]) -> None:
        if record_provenance:
            record_provenance(record)
        emit(
            "beat.judged",
            {
                "beat_index": beat.index,
                "iteration": record["iteration"],
                "score": record["score"],
                "passed": record["passed"],
                "feedback": record["feedback"],
                "run_id": record["run_id"],
            },
        )

    rendered = await run_pov_beat_loop(
        beat,
        job_id=job_id,
        sink=sink,
        product_assets=product_assets,
        on_video_submitted=checkpoint_video,
        on_iteration=record_iteration,
    )
    for step_id in checkpoint_step_ids:
        complete_checkpoint(job_id, step_id)
    return rendered


def _run_pov_campaign(
    *,
    job_id: str,
    topic: str,
    beat_plan: BeatPlan,
    emit: Callable[[str, dict[str, Any]], None],
    sink: Any,
    work_dir: Path,
    product_assets: Sequence[Asset] | None,
    record_provenance: Callable[[dict[str, Any]], None] | None,
    generate_music: bool = True,
) -> CampaignResult:
    """Run the long-running POV path in the worker, never in a request handler."""
    checkpoints = pending_checkpoints(job_id)

    async def render_all() -> list[POVBeatRender]:
        semaphore = asyncio.Semaphore(settings.pov_max_concurrency)

        async def render_one(beat: Any) -> POVBeatRender:
            emit("beat.started", {"beat_index": beat.index, "concept": beat.concept})
            async with semaphore:
                return await _render_or_resume_pov_beat(
                    job_id=job_id,
                    beat=beat,
                    # Pipeline owns and closes its sink. Each concurrent render
                    # therefore receives an independent B2 sink instance.
                    sink=build_sink(),
                    product_assets=product_assets,
                    checkpoints=checkpoints,
                    emit=emit,
                    record_provenance=record_provenance,
                )

        return await asyncio.gather(*(render_one(beat) for beat in beat_plan.beats))

    rendered_beats = asyncio.run(render_all())
    total_cost = 0.0
    beat_results: list[BeatResult] = []
    for beat, rendered in zip(beat_plan.beats, rendered_beats, strict=True):
        total_cost += rendered.cost_usd
        if rendered.run_id and record_provenance:
            record_provenance(
                {
                    "run_id": rendered.run_id,
                    "manifest_json": rendered.manifest_json or "{}",
                    "manifest_hash": rendered.manifest_hash or "",
                    "manifest_uri": rendered.manifest_uri,
                    "parent_run_id": rendered.parent_run_id,
                }
            )
        beat_results.append(
            BeatResult(
                index=beat.index,
                image_url=rendered.image_url,
                video_url=rendered.video_url,
                judge_score=rendered.judge_score,
                judge_iterations=rendered.judge_iterations,
                passed=rendered.passed,
            )
        )
        emit(
            "beat.generated",
            {
                "beat_index": beat.index,
                "image_url": rendered.image_url,
                "video_url": rendered.video_url,
            },
        )
        emit("beat.completed", {"beat_index": beat.index})

    music: GeneratedAudio | None = None
    if generate_music:
        emit("step.started", {"step": "audio", "message": "Generating music..."})
        music = generate_music_asset(
            topic,
            duration_sec=len(rendered_beats) * settings.pov_clip_duration_sec,
            sink=build_sink(),
            job_id=job_id,
        )
        _record_generated_audio(music, record_provenance)
        emit("step.completed", {"step": "audio", "enabled": True})
    else:
        emit("step.completed", {"step": "audio", "enabled": False, "skipped": True})

    emit("step.started", {"step": "voiceover", "message": "Generating voiceover..."})
    voiceover = generate_voiceover_asset(
        [beat.vo for beat in beat_plan.beats if beat.vo],
        sink=build_sink(),
        job_id=job_id,
        output_dir=work_dir,
        max_words=len(beat_plan.beats) * settings.pov_voiceover_max_words_per_beat,
        force=True,
    )
    _record_generated_audio(voiceover, record_provenance)
    emit("step.completed", {"step": "voiceover", "enabled": voiceover is not None})

    emit("step.started", {"step": "assemble", "message": "Assembling POV montage..."})
    reel_path = assemble_pov_montage(
        [readable_asset_url(rendered.video_url) for rendered in rendered_beats],
        readable_asset_url(music.url) if music else None,
        settings.pov_clip_duration_sec,
        output_dir=work_dir,
        captions=[beat.caption for beat in beat_plan.beats],
        voiceover_url=readable_asset_url(voiceover.url) if voiceover else None,
    )
    emit("step.completed", {"step": "assemble", "path": reel_path})

    emit("step.started", {"step": "storage", "message": "Uploading to B2..."})
    reel_url, manifest_hash, manifest_uri, run_id, verified = _store_final_reel(
        job_id=job_id,
        topic=topic,
        mode=RenderMode.pov,
        reel_path=reel_path,
        sink=sink,
        record_provenance=record_provenance,
    )
    emit("step.completed", {"step": "storage", "verified": verified, "run_id": run_id})
    emit("engine.completed", {"job_id": job_id, "run_id": run_id, "verified": verified})
    return CampaignResult(
        job_id=job_id,
        topic=topic,
        mode=RenderMode.pov,
        status=JobStatus.done,
        generate_music=generate_music,
        beat_plan=beat_plan,
        beats=beat_results,
        reel_url=reel_url,
        music_url=music.url if music else None,
        suggested_caption=beat_plan.suggested_caption,
        hashtags=beat_plan.hashtags,
        manifest_hash=manifest_hash,
        manifest_uri=manifest_uri,
        run_id=run_id,
        total_cost_usd=total_cost,
    )


def run_campaign(
    job_id: str,
    topic: str,
    mode: RenderMode,
    beat_count: int,
    emit: Callable[[str, dict[str, Any]], None],  # emit(event_type, data)
    product_assets: Sequence[Asset] | None = None,
    record_provenance: Callable[[dict[str, Any]], None] | None = None,
    generate_music: bool = True,
) -> CampaignResult:
    """Trace one campaign root while the engine records durable provenance."""
    with trace_operation(
        "reelproof.campaign",
        inputs={
            "job_id": job_id,
            "topic": topic,
            "mode": mode.value,
            "beat_count": beat_count,
            "generate_music": generate_music,
        },
        metadata={"has_product_assets": bool(product_assets)},
    ) as trace:
        with media_workspace() as work_dir:
            result = _run_campaign(
                job_id,
                topic,
                mode,
                beat_count,
                emit,
                product_assets=product_assets,
                record_provenance=record_provenance,
                work_dir=work_dir,
                generate_music=generate_music,
            )
        finish_trace(
            trace,
            {
                "job_id": job_id,
                "status": result.status.value,
                "run_id": getattr(result, "run_id", None),
                "manifest_hash": getattr(result, "manifest_hash", None),
                "total_cost_usd": getattr(result, "total_cost_usd", None),
            },
        )
        return result


def _run_campaign(
    job_id: str,
    topic: str,
    mode: RenderMode,
    beat_count: int,
    emit: Callable[[str, dict[str, Any]], None],  # emit(event_type, data)
    product_assets: Sequence[Asset] | None = None,
    record_provenance: Callable[[dict[str, Any]], None] | None = None,
    *,
    work_dir: Path,
    generate_music: bool = True,
) -> CampaignResult:
    """
    Full synchronous engine. Called from a background thread.
    `emit` sends progress events to the SSE queue.
    """
    emit("engine.started", {"job_id": job_id, "topic": topic, "mode": mode.value})

    try:
        work_dir = require_media_workspace(work_dir)
        if missing := settings.missing_campaign_settings(mode, generate_music=generate_music):
            raise RuntimeError("Campaign configuration is incomplete; set " + ", ".join(missing))
        if renderer_error := caption_renderer_error():
            raise RuntimeError(f"Campaign configuration is incomplete; {renderer_error}")

        # Fail before paid provider calls if B2 is unavailable.
        sink = build_sink()

        # 1. Plan
        emit("step.started", {"step": "planner", "message": "Planning beats..."})
        product_context = (
            "Use the uploaded product as the visual anchor." if product_assets else None
        )
        beat_plan: BeatPlan = plan_beats(
            topic,
            beat_count,
            product_context=product_context,
            voiceover_required=mode is RenderMode.pov,
        )
        emit("step.completed", {"step": "planner", "hook": beat_plan.hook, "beats": beat_count})

        if mode is RenderMode.pov:
            return _run_pov_campaign(
                job_id=job_id,
                topic=topic,
                beat_plan=beat_plan,
                emit=emit,
                sink=sink,
                work_dir=work_dir,
                product_assets=product_assets,
                record_provenance=record_provenance,
                generate_music=generate_music,
            )

        beat_results: list[BeatResult] = []
        title = beat_plan.hook.strip() or topic
        emit("step.started", {"step": "title-image", "message": "Generating title image..."})

        def record_title_iteration(record: dict[str, Any]) -> None:
            if record_provenance:
                record_provenance(record)

        title_image = run_beat_loop(
            Beat(
                index=-1,
                concept=(
                    f"A striking editorial cover image for {topic}. "
                    "Create a clean, photorealistic, faceless vertical scene with a strong focal subject, "
                    "cinematic lighting, and no text, logos, borders, or watermarks."
                ),
                caption=title,
            ),
            sink=sink,
            product_assets=product_assets,
            on_iteration=record_title_iteration,
        )
        total_agent_cost = title_image.total_cost_usd
        title_card_path = render_title_card(
            title,
            output_dir=work_dir,
            background_image_url=readable_asset_url(title_image.asset_url),
        )
        emit("step.completed", {"step": "title-image", "enabled": True})
        title_image_url = _store_local_intermediate(
            job_id=job_id,
            topic=topic,
            mode=mode,
            path=title_card_path,
            media_type="image/png",
            asset_kind="slideshow-title-card",
            record_provenance=record_provenance,
        )
        captioned_paths: list[str] = [title_card_path]

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
            captioned_path = burn_caption(
                readable_asset_url(url), beat.caption, beat.index, output_dir=work_dir
            )
            captioned_paths.append(captioned_path)
            captioned_url = _store_local_intermediate(
                job_id=job_id,
                topic=topic,
                mode=mode,
                path=captioned_path,
                media_type="image/png",
                asset_kind=f"captioned-beat-{beat.index}",
                record_provenance=record_provenance,
            )

            beat_results.append(
                BeatResult(
                    index=beat.index,
                    image_url=url,
                    captioned_url=captioned_url,
                    judge_score=loop_result.score,
                    judge_iterations=loop_result.iterations,
                    passed=loop_result.passed,
                )
            )
            emit("beat.completed", {"beat_index": beat.index})

        # 3. Optional background music. Voiceover is reserved for POV campaigns.
        music: GeneratedAudio | None = None
        if generate_music:
            emit("step.started", {"step": "audio", "message": "Generating music..."})
            total_dur = (
                settings.slideshow_title_duration_sec
                + len(beat_plan.beats) * settings.slideshow_beat_duration_sec
            )
            music = generate_music_asset(
                topic, duration_sec=total_dur, sink=build_sink(), job_id=job_id
            )
            _record_generated_audio(music, record_provenance)
            emit("step.completed", {"step": "audio", "enabled": True})
        else:
            emit("step.completed", {"step": "audio", "enabled": False, "skipped": True})

        # 4. Assemble
        emit("step.started", {"step": "assemble", "message": "Assembling slideshow..."})
        reel_path = assemble_slideshow(
            captioned_paths,
            readable_asset_url(music.url) if music else None,
            settings.slideshow_beat_duration_sec,
            output_dir=work_dir,
            title_duration=settings.slideshow_title_duration_sec,
        )
        emit("step.completed", {"step": "assemble", "path": reel_path})

        # 5. Store in B2
        emit("step.started", {"step": "storage", "message": "Uploading to B2..."})
        reel_b2_url, manifest_hash, manifest_uri, run_id, verified = _store_final_reel(
            job_id=job_id,
            topic=topic,
            mode=mode,
            reel_path=reel_path,
            sink=sink,
            record_provenance=record_provenance,
        )
        emit("step.completed", {"step": "storage", "verified": verified, "run_id": run_id})

        emit("engine.completed", {"job_id": job_id, "run_id": run_id, "verified": verified})

        return CampaignResult(
            job_id=job_id,
            topic=topic,
            mode=mode,
            status=JobStatus.done,
            generate_music=generate_music,
            beat_plan=beat_plan,
            beats=beat_results,
            title_image_url=title_image_url,
            reel_url=reel_b2_url,
            music_url=music.url if music else None,
            suggested_caption=beat_plan.suggested_caption,
            hashtags=beat_plan.hashtags,
            manifest_hash=manifest_hash,
            manifest_uri=manifest_uri,
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
            generate_music=generate_music,
            error=str(exc),
        )
