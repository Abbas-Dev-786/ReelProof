from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable

from genblaze_core import Asset, ObjectStorageSink, Pipeline

from ..config import settings
from ..schemas import Beat, BeatPlan, BeatResult, CampaignResult, JobStatus, RenderMode
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
    emit: Callable[[str, dict], None],  # emit(event_type, data)
) -> CampaignResult:
    """
    Full synchronous engine. Called from a background thread.
    `emit` sends progress events to the SSE queue.
    """
    emit("engine.started", {"job_id": job_id, "topic": topic, "mode": mode})

    try:
        # 1. Plan
        emit("step.started", {"step": "planner", "message": "Planning beats..."})
        beat_plan: BeatPlan = plan_beats(topic, beat_count)
        emit("step.completed", {"step": "planner", "hook": beat_plan.hook, "beats": beat_count})

        beat_results: list[BeatResult] = []
        captioned_paths: list[str] = []

        # 2. Per-beat: agent loop (generate + judge) → caption burn
        for beat in beat_plan.beats:
            emit("beat.started", {"beat_index": beat.index, "concept": beat.concept})

            url, score, iters = run_beat_loop(beat)
            passed = score >= settings.judge_pass_threshold

            emit("beat.judged", {
                "beat_index": beat.index,
                "score": round(score, 3),
                "iterations": iters,
                "passed": passed,
            })

            # Burn caption
            captioned_path = burn_caption(url, beat.caption, beat.index)
            captioned_paths.append(captioned_path)

            beat_results.append(BeatResult(
                index=beat.index,
                image_url=url,
                captioned_url=captioned_path,
                judge_score=score,
                judge_iterations=iters,
                passed=passed,
            ))
            emit("beat.completed", {"beat_index": beat.index})

        # 3. Music
        emit("step.started", {"step": "audio", "message": "Generating music..."})
        total_dur = len(beat_plan.beats) * settings.slideshow_beat_duration_sec
        music_url = generate_music(topic, duration_sec=total_dur)
        emit("step.completed", {"step": "audio"})

        # 4. Assemble
        emit("step.started", {"step": "assemble", "message": "Assembling slideshow..."})
        reel_path = assemble_slideshow(captioned_paths, music_url, settings.slideshow_beat_duration_sec)
        emit("step.completed", {"step": "assemble", "path": reel_path})

        # 5. Store in B2
        emit("step.started", {"step": "storage", "message": "Uploading to B2..."})
        sink = build_sink()
        reel_asset = Asset(
            url=f"file:///{os.path.abspath(reel_path).replace(os.sep, '/')}",
            media_type="video/mp4",
        )
        store_result = Pipeline.ingest(
            assets=[reel_asset],
            source="reelproof-assembly",
            source_metadata={"topic": topic, "mode": mode, "job_id": job_id},
            sink=sink,
            name=f"reel-store-{job_id}",
        )
        reel_b2_url = store_result.run.steps[0].assets[0].url
        manifest_hash = store_result.manifest.canonical_hash
        run_id = store_result.run.run_id
        verified = store_result.manifest.verify()
        emit("step.completed", {"step": "storage", "verified": verified, "run_id": run_id})

        # Cleanup local scratch
        for p in captioned_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
        try:
            os.unlink(reel_path)
        except OSError:
            pass

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
            run_id=run_id,
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
