# Faceless UGC Studio — 8-Day Hackathon Build Plan

> **Backblaze Generative Media Hackathon.** Official deadline: **Aug 3, 2026, 5pm ET** (~12 days out — plan to 8, keep 4 as buffer). Winners announced Aug 12.

---

## The product

**Faceless UGC Studio** — a topic (with optional product images) becomes a ready-to-post,
provenance-tracked TikTok asset:

- **One engine, two render backends:**
  - **Slideshow mode** (image per beat) — the reliability floor. Always works live, cheap, ships first.
  - **POV montage mode** (short animated clip per beat) — the hero upgrade. Pre-generated for the demo.
- **The moat = the self-healing loop.** A vision-judge scores every beat (hook strength, text
  legibility, artifacts, on-brand) and auto-regenerates the weak ones — the reject→fix→pass chain
  shown as a provenance lineage graph.
- **B2 is the system of record.** Every beat, audio track, and final render lands in B2 with a
  SHA-256 provenance manifest + a public "verify this asset" view.

### The engine (shared pipeline)

```
input (topic [+ product images])
   → ingest product images (Pipeline.ingest → B2 + provenance)      [if uploaded]
   → beat script (LLM): hook + N beats {visual concept, caption, optional VO}, + suggested caption/hashtags
   → per beat: generate visual
        · slideshow: text-to-image  OR  edit-model on product image (Bria/FLUX Kontext/Seedream image_url)
        · POV:       still → animate (i2v)  OR  t2v
   → overlay caption text (FFmpegTransform overlay_text, 9:16 safe-zone)
   → VisionJudge each beat → regenerate weak beats (AgentLoop, parent_run_id lineage)
   → audio: music (Stability Audio) + optional VO (ElevenLabs)
   → assemble 9:16 (FFmpegCompositor): slideshow reel OR POV montage
   → store all assets + manifest in B2; build lineage + verify view
```

---

## Stack

- **Backend:** Python 3.11+, FastAPI, Genblaze SDK, ffmpeg on PATH.
- **Async:** FastAPI background tasks + SSE for live per-beat progress (upgrade to Genblaze queue
  integration if time allows).
- **Frontend:** React/Vite SPA (or Next.js). HTMX+Jinja is a faster solo alternative if the UI stays simple.
- **Storage:** Backblaze B2 via `S3StorageBackend.for_backblaze(bucket)`.
- **Providers (lean, GMI-credit-friendly):**
  - `genblaze-core`, `genblaze-s3`
  - `genblaze-openai` — LLM script + **vision judge** + DALL·E/gpt-image + TTS
  - `genblaze-gmicloud` — cheap images (Reve $0.007, Seedream) + cheap video (Pixverse $0.03, Seedance $0.02, Kling) — **use GMI credits here**
  - `genblaze-elevenlabs` — voiceover / SFX
  - `genblaze-stability` — background music (`stable-audio-2.5`)
  - `genblaze-google` — Imagen/Veo (optional premium)
  - _Confirm exact extra names against the genblaze repo `pyproject` on Day 0._

---

## Day 0 — Prep (do before Day 1, ~2 hrs)

- Create **Backblaze B2** bucket + application key. Claim **GMI Cloud credits** (first 270 participants).
  Get **OpenAI**, **ElevenLabs**, **Stability** keys. Install **ffmpeg**.
- Python venv; `pip install` the genblaze extras above.
- Run stock examples to prove keys work: `quickstart.py`, `dalle_image_pipeline.py`,
  `b2_storage_pipeline.py`, `elevenlabs_tts_pipeline.py`, `fan_in_av_composite.py`.
- **Exit criteria:** every provider + B2 + ffmpeg confirmed working in isolation.

## Day 1 — Foundations & primitives spike

- Repo scaffold (FastAPI backend, frontend shell, `.env`).
- Prove each primitive end-to-end: generate 1 image → store in B2 → `manifest.verify()` == True;
  run 1 TTS clip; run 1 cheap i2v clip; mux image+audio → MP4 via `FFmpegCompositor`.
- **Exit criteria:** a script that outputs one captioned image in B2 with a verified manifest.

## Day 2 — Core engine: slideshow happy-path (no judge yet)

- LLM beat planner: topic → hook + 4–6 beats as JSON `{concept, caption}` + suggested caption/hashtags.
- Text-to-image per beat → ffmpeg `overlay_text` captions (9:16 safe-zone) → assemble timed
  slideshow MP4 (crossfade + ken-burns) + music.
- **Exit criteria:** topic in → full slideshow MP4 out, stored in B2. **This is the always-works floor.**

## Day 3 — Product mode + provenance surface

- Product image upload → `Pipeline.ingest()` (B2 + provenance) → edit models
  (Bria relight/genfill, FLUX Kontext, Seedream `image_url`) place product into beat scenes.
- Assemble the run's manifest/lineage into a "campaign package" (all assets + manifest, downloadable).
- **Exit criteria:** upload product pics → on-brand slideshow; every asset traceable in B2.

## Day 4 — The moat: self-healing agent loop

- `VisionJudge` evaluator (vision LLM): score each beat on hook / **text legibility** / artifacts /
  on-brand → threshold → regenerate weak beats with refined prompt via `AgentLoop` (cap 1–2 iters).
- Capture reject→fix→pass lineage via `parent_run_id`.
- **Exit criteria:** slideshow where weak slides visibly self-correct; lineage recorded. **Demo money-shot.**

## Day 5 — Frontend + streaming UX

- UI: enter topic, upload images, pick mode, generate.
- Stream per-beat progress (Genblaze streaming events → SSE): "beat 3 judged 0.6 → regenerating → passed."
- Final slideshow player + downloadable Photo-Mode images + suggested caption/hashtags.
- Provenance/lineage view + "verify this asset" panel.
- **Exit criteria:** whole flow usable in the browser.

## Day 6 — POV montage (hero upgrade)

- POV render backend: per beat, still → animate (i2v Pixverse/Kling) or t2v; concat clips → montage
  with captions + music. Same judge loop applies to clips.
- Async job (background task + resume); pre-generate one showcase.
- **Exit criteria:** POV montage mode works (async); one showcase pre-rendered.

## Day 7 — Polish, reliability, demo-proofing

- Error handling + Genblaze retry policy + **provider fallback** (Kling→Pixverse, etc.).
- Moderation hook on inputs/outputs (on-rubric, production-minded).
- **Pre-generate 2–3 killer showcase campaigns** (both modes) so the demo never depends on a live render.
- Design polish.
- **Exit criteria:** bulletproof demo path + pre-baked showcases.

## Day 8 — Devpost submission

- Record 2–3 min demo video: problem → live slideshow gen → **the self-heal moment** →
  provenance/verify → POV showcase → B2 as system of record.
- Writeup: problem, how it uses **B2 (provenance/system of record)** + **Genblaze (agent loop +
  multi-provider + fallback)**, architecture diagram, production path.
- **Exit criteria:** submitted with buffer to spare.

---

## Cut list (if slipping) — always protect the end-to-end slideshow + provenance + judge loop

1. Drop POV montage (slideshow-only still wins).
2. Keep only one input mode (topic OR product).
3. Drop music/VO (captions + stills are enough).
4. Reduce to 4 beats; judge on text-legibility only.

## What actually wins this hackathon (keep these visible)

- **B2 as system of record** — manifests, lineage graph, verify view (not a download folder).
- **Genblaze used as designed** — the agent loop + genuine multi-provider + fallback.
- **The self-heal loop on screen** — the "generate, evaluate, retry, store" theme, made visible.
- **Production-minded** — async, retries, fallback, moderation.

## Top risks & mitigations

| Risk | Mitigation |
|---|---|
| AI garbles on-slide text | Generate clean backgrounds; burn captions with ffmpeg `overlay_text` |
| Video render too slow for live demo | Slideshow is the live path; POV is pre-generated async |
| Cross-clip/beat inconsistency | Shared style seed + `image_url` conditioning + vision-judge enforces it |
| Provider outage/error mid-demo | Retry policy + fallback provider; pre-baked showcases |
| Exact genblaze package names differ | Verify against repo `pyproject` on Day 0 |
