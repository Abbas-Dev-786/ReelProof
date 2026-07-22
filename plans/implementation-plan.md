# ReelProof — Implementation Plan (Hackathon MVP)

## Context

`docs/` fully specifies **ReelProof v2** (authoritative): a faceless short-form studio that turns a
topic (+ optional product images) into a 9:16 slideshow or POV montage, self-heals weak beats with a
vision-judge `AgentLoop`, and stores every asset + a hash-verified provenance manifest in Backblaze
B2. The plan is **sound and grounded in a real SDK** — every API in `ARCHITECTURE.md` was verified
against `genblaze/docs/features/*` and `genblaze/examples/*`.

**But almost nothing is built.** Current reality:
- `server/main.py` = 15 lines that print whether `GMI_API_KEY` loaded. **No FastAPI app.**
- `client/src/App.tsx` = `<p>Hello</p>`. A fresh shadcn/Vite/React-19 scaffold, no product UI.
- `server/.venv` exists but **genblaze is NOT installed** (`import genblaze_core` → ModuleNotFoundError).
- `server/.env` has **only `GMI_API_KEY`** (user says the rest exist and will be added).
- Python 3.12.9 ✓, ffmpeg ✓ both present.
- `docs/user-stories.md` is **stale v1** (marketer/campaign) — ignore/archive; PRD v2 wins.

Goal: get the **slideshow floor** working end-to-end first (topic → captioned 9:16 MP4 in B2 with a
verified manifest), then layer the self-healing judge loop, the streaming frontend, and finally POV
montage as the stretch. Mirrors `docs/BUILD-PLAN.md`'s cut-list priority: **always protect
end-to-end slideshow + provenance + judge loop.**

## Key SDK facts confirmed (build against these)

- **Pipeline**: `Pipeline(name, chain=?, tenant_id=?).step(provider, model=, prompt=, modality=, **params).run(sink=, timeout=, pipeline_timeout=, on_submit=, on_step_complete=)` → `PipelineResult(.run, .manifest)`. `.arun()`/`.abatch_run(max_concurrency=)` for async. `result.run.steps[i].assets[j].url/.sha256`.
- **Chaining**: `Pipeline(chain=True)` feeds step N-1 output → step N (image→video). `external_inputs=[Asset]` seeds an uploaded image into step 0 (provider must `accepts_chain_input`). `input_from=[i,j]` fans in for mux.
- **AgentLoop**: `AgentLoop(build_pipeline, evaluator, max_iterations=)`. `build_pipeline(ctx)` reads `ctx.iteration` / `ctx.last_evaluation.feedback`. Evaluator returns `EvaluationResult(passed, score, feedback)`; subclass `Evaluator` for the vision judge. Auto `parent_run_id` lineage. `loop.run()`/`loop.stream()`; `AgentResult.iterations`, `.total_cost_usd`.
- **Captions**: `FFmpegTransform(output_dir=).step(..., operation="overlay_text", text=, fontsize=, x=, y=, fontcolor=, step_type=StepType.EDIT)`.
- **Mux**: `FFmpegCompositor().step(..., step_type=StepType.MIX, input_from=[v,a])` muxes **one** video + **one** audio.
- **Storage**: `ObjectStorageSink(S3StorageBackend.for_backblaze(bucket, region=, public_url_base=), prefix=, key_strategy=KeyStrategy.HIERARCHICAL, parquet_sink=ParquetSink("data/"), manifest_lock=ObjectLockConfig(mode="GOVERNANCE", retain_until=...))`. Read back: `sink.read_manifest(run, verify=True)`; `manifest.verify()` (enforces per-asset sha256 in 0.3.4+).
- **Streaming**: `pipe.stream()` / `loop.stream()` yield a discriminated union; `event.type` ∈ {pipeline.started, step.queued, step.started, step.progress, step.completed, step.failed, pipeline.completed/failed, agent.iteration.started, agent.iteration.evaluated, agent.completed}. `event.to_dict()` is JSON-safe (drops in-process `step`/`result`). Heartbeats on long polls.
- **Planner + judge LLM**: `genblaze_openai.chat(model, messages=|prompt=, system=, tools=, temperature=)` → `ChatResponse(.text, .tool_calls, .tokens_in/out)`. **Not** pipeline-integrated and `cost_usd` is always `None` here — stash planner/judge details in downstream `step.metadata`.
- **Pricing**: SDK ships zero prices; register per model (`provider.models.register_pricing(slug, per_unit(x))`) or `cost_usd` stays `None`.
- **Ingest**: `Pipeline.ingest(assets=[Asset(url=,media_type=)], source=, source_metadata=, sink=)` for provenance-stamped product uploads.

## Known hurdles (design around these)

1. **Version drift (top risk).** Docs are 0.3.x; `requirements.txt` pins `genblaze==0.4.3` / `genblaze-core==0.3.6`. Day-0 must install and smoke-test; reconcile any 0.4 signature/slug changes against the actual installed package (`python -c "import genblaze_core, inspect; ..."`) before trusting a doc.
2. **Slideshow assembly is NOT a documented built-in.** `FFmpegCompositor` only muxes 1 video + 1 audio; `FFmpegTransform` does single-asset ops. Concatenating **N stills → timed 9:16 video with crossfade/ken-burns + music** needs a **custom step** (a `SyncProvider` subclass shelling out to ffmpeg, or a direct ffmpeg concat/xfade+zoompan+amix invocation). Treat this as real work, not a one-liner.
3. **Model slugs drift / dead models.** `reve-create`, `pixverse-v5.6-i2v`, etc. must be validated against the installed `model-matrix` at preflight; keep a `fallback_models` per role.
4. **B2 bucket must be created with Object Lock enabled** (can't be toggled later) for the immutability story.
5. **Judge must be a different model than the generator** and use anchored sub-scores, or it inflates and no retries fire — seed one deliberately weak beat for the demo.
6. **Caption legibility** (safe-zone, wrapping, contrast) is the #1 slideshow failure and always eats time.

## Architecture (build order = dependency order)

```
server/
  app/
    main.py            FastAPI app, CORS, router mount
    config.py          pydantic-settings: keys, bucket, region, public_url_base
    schemas.py         API request/response + BeatPlan pydantic models
    storage.py         build_sink() → ObjectStorageSink(B2 + Parquet + ObjectLock); read_manifest/verify helpers
    engine/
      planner.py       topic(+product) → BeatPlan via genblaze_openai.chat(tools=)
      beat_render.py   per-beat Pipeline: t2i  |  edit(external_inputs)  |  chain t2i→i2v (POV)
      judge.py         VisionJudge(Evaluator): gpt-4o vision scores url → EvaluationResult
      loop.py          AgentLoop wiring: build_pipeline(ctx) folds feedback, max_iterations=2
      captions.py      FFmpegTransform overlay_text, 9:16 safe-zone
      audio.py         Stability stable-audio-2.5 (music) [+ ElevenLabs VO optional]
      assemble.py      CUSTOM ffmpeg step: N stills→timed slideshow | concat clips→montage + amix
      run_engine.py    orchestrates planner→loop(per beat)→captions→audio→assemble→store; emits events
    jobs/
      store.py         SQLite job table: status, result JSON, on_submit checkpoints (prediction ids)
      worker.py        FastAPI BackgroundTasks: runs run_engine, pushes StreamEvents to an asyncio.Queue
    api/
      routes.py        endpoints below
```

### Endpoints (from ARCHITECTURE.md §2)
- `POST /campaigns` → create job (topic, mode, format, options) → `{job_id}`
- `POST /campaigns/{id}/assets` → upload product image → `Pipeline.ingest()` → B2
- `GET  /campaigns/{id}/stream` → **SSE**, relays `event.to_dict()` from the job queue
- `GET  /campaigns/{id}` → status + result (asset URLs, caption, hashtags, lineage)
- `GET  /campaigns/{id}/lineage` → provenance graph (manifest + Parquet)
- `GET  /verify/{run_id}` → `sink.read_manifest` → `manifest.verify()` → verdict + provider/model/prompt/params/lineage

### Frontend (`client/src`, React 19 + Vite + shadcn already scaffolded)
- `pages/Create.tsx` — topic input, product upload, mode/format select, Generate
- `pages/Run.tsx` — `EventSource(/campaigns/{id}/stream)` → live per-beat tray ("beat 3 judged 0.6 → regenerating → passed"), then player + downloadable stills + caption/hashtags
- `pages/Verify.tsx` — verify view (hash verdict + provenance detail + reject→fix→pass lineage)
- `lib/api.ts` — typed fetch wrappers + SSE hook (`useEventStream`)

## Phased execution

**Phase 0 — Day 0 setup (gating).** Activate `server/.venv`; `pip install -r requirements.txt`; add missing keys to `.env` (OpenAI/B2/ElevenLabs/Stability); create B2 bucket **with Object Lock enabled**; run stock examples (`quickstart.py`, `dalle_image_pipeline.py`, `b2_storage_pipeline.py`, `elevenlabs_tts_pipeline.py`, `fan_in_av_composite.py`) to confirm each provider + B2 + ffmpeg + **the installed 0.4.3 API**. Exit: every provider works in isolation and the 0.4.3 signatures match (or deltas noted).

**Phase 1 — Primitives + storage.** `config.py`, `storage.py` (`build_sink`). Prove: 1 image → B2 → `manifest.verify()==True`; 1 TTS clip; mux image+audio via `FFmpegCompositor`. Register pricing so `cost_usd` populates.

**Phase 2 — Slideshow happy-path (no judge).** `planner.py` (BeatPlan JSON), `beat_render.py` (t2i per beat), `captions.py`, `audio.py`, **`assemble.py` (custom ffmpeg slideshow builder — the hard part)**, `run_engine.py` (sync). Exit: topic in → full slideshow MP4 in B2. **This is the always-works floor.**

**Phase 3 — Product mode + provenance surface.** `Pipeline.ingest()` upload → edit-model beats (`external_inputs`); campaign package (assets + manifest); `/verify` endpoint. Exit: upload product pics → on-brand slideshow, every asset traceable.

**Phase 4 — The moat: self-healing loop.** `judge.py` (VisionJudge scoring hook/legibility/artifacts/on-brand), `loop.py` (AgentLoop, max_iterations=2, feedback→prompt), `parent_run_id` lineage. Exit: weak slides visibly self-correct; lineage recorded. **Demo money-shot.**

**Phase 5 — Frontend + streaming.** FastAPI SSE relay + `jobs/`, then `Create`/`Run`/`Verify` pages with the live tray. Exit: whole flow usable in browser.

**Phase 6 — POV montage (stretch).** `beat_render.py` chain t2i→i2v (Pixverse/Seedance), concat clips in `assemble.py`; async job + `on_submit` checkpoint/resume; pre-generate one showcase. Exit: POV works async, one showcase pre-rendered.

**Phase 7 — Polish/demo-proofing.** `fallback_models` per step, retry policy, `ModerationHook` on ingest/outputs, pre-bake 2–3 showcases, design polish.

## Verification

- **Per phase, run the engine for real** against one topic and confirm the MP4 plays and `manifest.verify() == True`.
- Storage: after a run, `sink.read_manifest(run).verify()` and open the asset URL in a browser (needs `public_url_base` or presign).
- Judge loop: seed a deliberately weak beat; confirm a `agent.iteration.evaluated` (fail) → regenerate → pass in the stream, and `parent_run_id` chain in the manifest.
- SSE: `curl -N http://localhost:8000/campaigns/{id}/stream` shows JSON events; frontend tray updates live.
- `genblaze verify <manifest.json>` CLI matches the `/verify` endpoint verdict.
- Cost: `AgentResult.total_cost_usd > 0` (pricing registered).

## Open decisions taken (not blocking)
- Job store = **SQLite** for dev (per ARCHITECTURE); Redis only if time.
- Build **slideshow first, POV as stretch** (per BUILD-PLAN cut-list).
- `docs/user-stories.md` will be **archived** (superseded by PRD v2) — not implemented.
