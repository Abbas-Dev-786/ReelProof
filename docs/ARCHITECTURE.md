# Technical Architecture — ReelProof

> Companion to `docs/PRD.md` and `docs/BUILD-PLAN.md`. Grounded in the local Genblaze docs
> (`genblaze/docs/features/*`). Stack: **React/Vite SPA + FastAPI + Genblaze SDK + Backblaze B2**.

---

## 1. System context (C4 level 1)

```text
                         ┌───────────────────────────────────────────────┐
                         │                   ReelProof                     │
                         │                                                 │
   ┌──────────┐  HTTPS   │  ┌────────────┐        ┌───────────────────┐   │
   │  Creator │◄────────►│  │ React/Vite │  REST  │   FastAPI backend  │   │
   │ (browser)│   SSE    │  │    SPA     │◄──────►│  (API + job orch.) │   │
   └──────────┘          │  └────────────┘        └─────────┬─────────┘   │
                         │                                   │ Genblaze SDK │
                         └───────────────────────────────────┼─────────────┘
                                                             │
             ┌───────────────────────────────┬──────────────┼───────────────────────────┐
             ▼                               ▼               ▼                           ▼
    ┌─────────────────┐          ┌──────────────────┐  ┌───────────────┐        ┌────────────────┐
    │  LLM + Vision    │          │ Media providers  │  │  Backblaze B2 │        │  ffmpeg (local) │
    │  (OpenAI)        │          │ GMICloud / Reve  │  │  assets +     │        │ compositor +    │
    │  script + judge  │          │ Pixverse / Bria  │  │  manifests +  │        │ transforms      │
    │                  │          │ ElevenLabs /     │  │  Object Lock  │        │ (captions/mux)  │
    │                  │          │ Stability Audio  │  │  + Parquet    │        │                 │
    └─────────────────┘          └──────────────────┘  └───────────────┘        └────────────────┘
```

- **SPA** collects input, opens an SSE stream for live progress, renders the result + provenance.
- **FastAPI** owns job lifecycle, runs Genblaze pipelines in **background workers**, relays Genblaze
  stream events to the browser as SSE, and exposes a **verify** endpoint.
- **Genblaze** orchestrates providers, assembles media, and writes provenance to **B2**.

---

## 2. Container / component view (C4 level 2)

```text
FastAPI backend
├── api/
│   ├── POST /campaigns              create job (topic, mode, format, options)
│   ├── POST /campaigns/{id}/assets  upload product image → Pipeline.ingest() → B2
│   ├── GET  /campaigns/{id}/stream  SSE: relays Genblaze StreamEvents
│   ├── GET  /campaigns/{id}         status + result (asset URLs, caption, hashtags)
│   ├── GET  /campaigns/{id}/lineage provenance graph (from manifest + Parquet)
│   └── GET  /verify/{run_id}        fetch manifest, recompute hash, return verdict
│
├── jobs/                            background worker layer
│   ├── job_store (Redis/SQLite)     job state + on_submit checkpoints (prediction ids)
│   └── worker                       runs the engine; resumable via saved prediction ids
│
└── engine/                          the ReelProof pipeline (pure Genblaze)
    ├── planner.py                   topic (+product) → BeatPlan (LLM, structured)
    ├── beat_render.py               per-beat: image OR clip  (+ product edit)
    ├── judge.py                     VisionJudge(Evaluator)  → EvaluationResult
    ├── loop.py                      AgentLoop wiring (max_iterations, feedback→prompt)
    ├── captions.py                  FFmpegTransform overlay_text (9:16 safe-zone)
    ├── audio.py                     Stability music (+ ElevenLabs VO)
    ├── assemble.py                  FFmpegCompositor → 9:16 MP4 (slideshow | montage)
    └── storage.py                   ObjectStorageSink(B2) + Object Lock + ParquetSink
```

---

## 3. The generation pipeline (data flow)

```text
[topic] (+ [product images] ── Pipeline.ingest ──► B2 asset+manifest, provenance stamped)
   │
   ▼
Planner (LLM, structured JSON)
   → BeatPlan { hook, beats:[ {concept, caption, vo?} ], suggested_caption, hashtags[] }
   │
   ▼   for each beat  (concurrent where safe: arun / abatch_run)
┌───────────────────────────── AgentLoop per beat ─────────────────────────────┐
│ build_pipeline(ctx):                                                          │
│   prompt = beat.concept (+ ctx.last_evaluation.feedback if retry)             │
│   SLIDESHOW: Pipeline.step(image_provider, prompt, modality=IMAGE)            │
│             [product beat]: external_inputs=[ingested_asset] → edit model      │
│   POV:       Pipeline.step(image_provider…) .step(video_provider, chain=True) │
│                → still animated to clip (i2v)                                  │
│                                                                               │
│ VisionJudge.evaluate(result):                                                 │
│   score = vision_model.score(asset.url)  # hook/legibility/artifacts/on-brand │
│   passed = score >= threshold; feedback if failed                             │
│                                                                               │
│ stop when passed OR max_iterations (1–2). parent_run_id links each attempt.   │
└───────────────────────────────────────────────────────────────────────────────┘
   │  (winning beat asset per beat)
   ▼
Captions: FFmpegTransform overlay_text on each beat visual (safe-zone, brand font)
   │
   ▼
Audio: Stability stable-audio-2.5 (music)  [+ ElevenLabs TTS voiceover]
   │
   ▼
Assemble: FFmpegCompositor
   SLIDESHOW: timed stills + crossfade/ken-burns + music  → 9:16 MP4
   POV:       concat clips + captions + music              → 9:16 MP4
   (fan-in via input_from=[…])
   │
   ▼
Store: run(sink = ObjectStorageSink(S3StorageBackend.for_backblaze(bucket),
                                    key_strategy=HIERARCHICAL,
                                    manifest_lock=ObjectLockConfig(GOVERNANCE),
                                    parquet_sink=ParquetSink()))
   → B2: assets + canonical manifest (hash-verified); lineage in Parquet
   │
   ▼
Result surfaced to SPA: player, downloadable stills, caption/hashtags, lineage graph, verify link
```

---

## 4. Async job + streaming (production-minded)

```text
Browser                 FastAPI                 Worker                  Genblaze/Providers      B2
  │  POST /campaigns       │                       │                          │                 │
  │──────────────────────► │  enqueue job          │                          │                 │
  │  { job_id }            │──────────────────────►│                          │                 │
  │◄───────────────────────│                       │  Pipeline.run/arun(      │                 │
  │  GET .../stream (SSE)   │                       │    on_submit=checkpoint, │                 │
  │──────────────────────► │  subscribe emitter    │    on_step_complete=…,   │                 │
  │                        │◄─────── StreamEvents ──│    sink=B2 )             │                 │
  │◄── step.started ───────│                       │  submit()───────────────►│  (prediction id)│
  │◄── step.progress ──────│  (relay to_dict())    │◄── on_submit(sid,pid) ───│  → checkpoint   │
  │◄── agent.iteration ────│                       │      poll…               │                 │
  │◄── step.completed ─────│                       │  fetch_output───────────►│  assets ───────►│ upload
  │◄── pipeline.completed ─│                       │  manifest.verify()       │                 │ manifest
  │  GET /campaigns/{id}    │  result payload       │                          │                 │
```

- **`on_submit(step_id, prediction_id)`** persists provider job ids → a worker restart resumes
  polling instead of re-billing a video generation.
- **SSE** carries `event.to_dict()` (JSON-safe; `step`/`result` objects excluded). The SPA renders
  the "Up next / running / judged → regenerating → passed" tray from these events.
- Long polls (Sora/Veo/Stable-Audio) emit **heartbeats** — keep the SSE proxy alive.

---

## 5. Provenance & verify path

```text
Generation run ──► Manifest.from_run() ──► canonical_json (sorted keys, NFC, float-normalized)
                                              │
                                              ▼  SHA-256 over _hash_payload (excludes ids/urls/timestamps)
                                        canonical_hash
                                              │
        ObjectStorageSink transfers assets ──► recompute per-asset sha256 ──► rebind into manifest
                                              │
                                              ▼
        B2:  {prefix}/runs/{tenant}/{date}/{run_id}/manifest.json   (+ assets/)
             optional Object Lock (GOVERNANCE) → immutable for retention window
                                              │
   Verify endpoint / public view:            ▼
        sink.read_manifest(run) → manifest.verify()  (hash + declared sha256)
        [optional] fetch asset bytes, hash, compare to asset.sha256  (== genblaze verify --fetch)
        render: provider, model, prompt(policy-filtered), params, timestamps, pass/fail lineage
```

Trust note: the hash proves **integrity**, not authorship. For the demo we present it as "tamper-
evident provenance" and mention Object Lock as the tamper-*prevention* layer.

---

## 6. Storage layout (B2)

```text
reelproof/                                   # prefix
  runs/{tenant}/{YYYY-MM-DD}/{run_id}/
    manifest.json                            # canonical, hash-verified (optionally Object-Locked)
    assets/
      {asset_id}.png                         # beat stills
      {asset_id}.mp3                          # music / VO
      {asset_id}.mp4                          # per-beat clips (POV) + final reel
  ingest/{tenant}/…                           # provenance-stamped product uploads
data/ (local or B2)                           # ParquetSink: runs / steps / assets tables → lineage queries
```

- **Key strategy:** `HIERARCHICAL` (run-grouped, easy to browse for the demo). `CONTENT_ADDRESSABLE`
  optional for dedup + immutable Cache-Control (zero-egress via Cloudflare) later.
- **Serving:** set `public_url_base` (Cloudflare CNAME) for browser-loadable durable URLs; otherwise
  presign at read time. Never store presigned URLs in manifests.

---

## 7. Key SDK touchpoints (cheat-sheet)

| Need | Genblaze API |
|------|--------------|
| Multi-step gen + manifest | `Pipeline(...).step(...).run(sink=…)` / `.arun()` |
| Feed uploaded product image into step 0 | `.step(edit_provider, external_inputs=[asset])` |
| Chain still → clip | `Pipeline(chain=True).step(image).step(video)` |
| Fan-in video+audio → mux | `.step(FFmpegCompositor(), input_from=[i,j], step_type=MIX)` |
| Burn captions | `.step(FFmpegTransform(), operation="overlay_text", …)` |
| Self-healing loop | `AgentLoop(build_pipeline, Evaluator, max_iterations=…)` |
| Iteration lineage | automatic `parent_run_id` via `Pipeline.from_result(prev)` |
| Live progress | `pipeline.stream()` / `loop.stream()` → `event.to_dict()` → SSE |
| Crash-safe video jobs | `run(on_submit=checkpoint, on_step_complete=…)` |
| Durable storage + provenance | `ObjectStorageSink(S3StorageBackend.for_backblaze(bucket))` |
| Immutable provenance | `manifest_lock=ObjectLockConfig(mode="GOVERNANCE", retain_until=…)` |
| Queryable lineage | `parquet_sink=ParquetSink("data/")` |
| Model fallback | `.step(..., fallback_models=[...])` |
| Verify | `sink.read_manifest(run)` → `manifest.verify()`; CLI `genblaze verify` |
| Cost | register pricing strategy per model; `AgentResult.total_cost_usd` |

---

## 8. Tech stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | React + Vite (TS) | SSE via `EventSource`; player, upload, lineage graph, verify view |
| Backend | FastAPI (Python 3.11+) | REST + SSE; background tasks for jobs |
| Orchestration | Genblaze SDK | core + s3 + provider extras |
| Job state | SQLite (dev) → Redis (prod) | job status + `on_submit` checkpoints |
| Media | ffmpeg (on PATH) | via `FFmpegCompositor` / `FFmpegTransform` |
| Storage | Backblaze B2 | `genblaze-s3`; Object Lock bucket for immutability |
| Analytics | ParquetSink | lineage/cost queries powering the graph view |

---

## 9. Reliability & security notes

- **Fallback + retry:** every provider step declares `fallback_models`; SDK retry policy handles
  transient 429/5xx with jittered backoff.
- **Moderation:** `ModerationHook` on ingested uploads and on outputs before serving.
- **Timeouts:** `pipeline_timeout` (wall-clock) + per-step `timeout`; POV runs on the async path.
- **URL hygiene:** durable/public URLs in manifests; presigned URLs never persisted (`__str__`
  redacts signatures). `public_url_base` for browser fetches.
- **Secrets:** provider keys + `B2_KEY_ID`/`B2_APP_KEY` in `.env`, never in `provider_payload`.
- **Model drift:** slugs validated at preflight; matrix has `suspected_dead` entries — keep a
  fallback per role.

---

## 10. Demo-day architecture (what runs live vs pre-baked)

- **Live:** slideshow generation end-to-end (fast, cheap), including one **deliberately weak beat**
  so the judge loop visibly triggers; the verify view on a freshly generated asset.
- **Pre-baked:** 2–3 POV montage showcases (async render done ahead of time), plus a Parquet-backed
  lineage graph. One short POV clip may be kicked off live to prove it's real.
