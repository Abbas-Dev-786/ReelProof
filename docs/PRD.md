# Product Requirements Document (PRD)

## Product Name

**ReelProof** _(working name — a faceless UGC studio that proves how every frame was made)_

**Category:** Provenance-native generative media studio for short-form social content

**Version:** v2.0 (Hackathon MVP) — supersedes v1.0 "Autonomous AI Campaign Team"

> Context: this PRD replaces the earlier multi-agent "campaign team" concept. Same creator-tooling
> DNA, but re-scoped around what actually wins the Backblaze Generative Media Hackathon and what is
> reliably buildable on the Genblaze SDK in 8 days. See `docs/BUILD-PLAN.md` and
> `docs/ARCHITECTURE.md`.

---

## 1. Executive Summary

ReelProof turns a **topic** (optionally plus **uploaded product images**) into a ready-to-post,
**faceless** short-form asset — either a **TikTok-style slideshow** or a **POV "day-in-my-life"
montage** — and stores every generated asset in Backblaze B2 with a **cryptographically verifiable
provenance manifest**.

The product has one engine with two render backends:

- **Slideshow mode** — one still image per "beat", captioned, assembled into a 9:16 reel. Fast,
  cheap, demo-safe. This is the reliability floor.
- **POV montage mode** — one short animated clip per beat, stitched into a motion montage. Higher
  wow, rendered async. This is the hero upgrade.

Two things make ReelProof more than a wrapper around a video model:

1. **A self-healing quality loop.** A vision-model judge scores every beat (hook strength, on-slide
   text legibility, visual artifacts, on-brand look) and **automatically regenerates the weak ones**
   using Genblaze's `AgentLoop`. The reject → refine → pass chain is captured as provenance lineage
   and shown to the user.
2. **B2 as the system of record.** Every beat, audio track, and final render carries a SHA-256
   manifest, optionally under **Object Lock** (immutable). A public "verify this asset" view reads
   provenance back out — addressing AI-disclosure / authenticity needs head-on.

### Why faceless

Faceless short-form (Photo Mode carousels, POV lifestyle montages) is a top-performing organic and
paid format today, and it sidesteps the single hardest generative-video problem: talking-avatar
lip-sync (which none of Genblaze's native video providers support). No face means no custom lip-sync
adapter and no uncanny-valley risk — every pixel is producible on native Genblaze providers.

---

## 2. Problem Statement

Short-form creators and small ecommerce brands need a constant stream of fresh faceless content.
Today they either:

- stitch together 4–5 disconnected AI tools (script, image, voice, captions, editor), or
- pay for tools that spit out low-quality slides with **garbled on-image text** (the #1 failure of
  every AI slideshow generator) and **no quality control** — you get whatever the model produced,
  good or bad.

And as AI-disclosure expectations rise (platform labels, FTC guidance, C2PA/Content Credentials),
**nobody can prove how a given asset was generated** — there is no portable, verifiable record.

There is no tool that (a) produces a complete, postable faceless asset end-to-end, (b) *judges and
fixes its own output* before handing it over, and (c) ships every asset with durable, verifiable
provenance.

---

## 3. Vision

Every piece of AI-generated media should arrive **finished, quality-checked, and provable**.
ReelProof is the studio that generates faceless short-form content, self-corrects it, and gives the
creator a durable, verifiable record of exactly how each asset was made.

---

## 4. Goals

### Product goals
- Topic → complete, postable 9:16 asset (slideshow) in under ~90 seconds.
- Optional product-image upload woven into the visuals via image-editing models.
- Visible, automatic quality improvement — weak beats are caught and fixed.
- Every asset downloadable *and* independently verifiable.

### Technical goals (hackathon rubric alignment)
- Demonstrate an **agentic generate → evaluate → retry → store** loop (Genblaze `AgentLoop`).
- Use **B2 as the system of record**: assets + manifests + lineage + Object Lock, not a download folder.
- Use **Genblaze as designed**: multi-provider orchestration, model fallback, streaming, provenance.
- Show a clear **path to production**: async jobs, checkpoint/resume, retries, moderation, cost tracking.

### Non-goals (v2.0)
Talking-avatar lip-sync, a video-editing timeline, team collaboration, direct social publishing,
ads-manager integration, billing, analytics dashboards, a creator marketplace.

---

## 5. Target Users

**Primary:** faceless short-form creators (niche/aesthetic/educational TikTok & Reels), solo
ecommerce/D2C founders needing product carousels.

**Secondary:** social/marketing freelancers and small agencies; anyone who needs *verifiable*
AI-media provenance (compliance-conscious brands).

---

## 6. User Journey

```text
Enter topic  ──(optional)──►  Upload product image(s)
      │                              │
      ▼                              ▼
Choose mode (Slideshow / POV montage) + format (9:16)
      │
      ▼
Generate  ──►  live per-beat progress (streaming)
      │
      ▼
Beat script (LLM)  ──►  per-beat visual (image OR clip)
      │
      ▼
Vision judge scores each beat  ──►  weak beats auto-regenerate (loop)
      │
      ▼
Add captions + music (+ optional VO)
      │
      ▼
Assemble 9:16 reel  ──►  store all assets + manifest in B2
      │
      ▼
Result: player + downloadable assets + caption/hashtags + provenance/verify view
```

---

## 7. Scope

### Included (v2.0 MVP)
- Topic input; optional product-image upload (ingested with provenance).
- LLM beat planner (hook + N beats, caption/hashtag suggestions).
- Slideshow render backend (still-per-beat → captioned 9:16 reel).
- POV montage render backend (clip-per-beat → motion 9:16 montage, async).
- Self-healing vision-judge loop (score → regenerate weak beats → re-score).
- Music (Stability Audio) + optional voiceover (ElevenLabs TTS).
- B2 storage of every asset + manifest; provenance/lineage view; public verify.
- Streaming progress UI; downloadable Photo-Mode images + caption/hashtags.

### Excluded (v2.0)
See §4 Non-goals.

---

## 8. Core Features

| # | Feature | What it does | Genblaze surface used |
|---|---------|--------------|-----------------------|
| F1 | Topic input | Free-text topic/angle → drives the beat plan | (app) LLM call |
| F2 | Product image ingest | Upload product photo(s), provenance-stamped in B2 | `Pipeline.ingest()`, `ObjectStorageSink` |
| F3 | Beat planner | Topic → hook + N beats `{visual concept, on-screen caption, optional VO}` + suggested caption/hashtags | LLM call (structured output) |
| F4 | Slide/scene generation | Per beat: text-to-image, OR edit an uploaded product image into the scene | text-to-image providers; edit models (`external_inputs`) |
| F5 | Caption burn-in | Crisp, legible caption text over the visual, 9:16 safe-zone | `FFmpegTransform` `overlay_text` |
| F6 | Self-healing judge | Vision LLM scores each beat; weak beats regenerate with refined prompt; lineage recorded | `AgentLoop`, custom `Evaluator`, `parent_run_id` |
| F7 | Audio | Background music; optional voiceover per beat/overall | Stability Audio; ElevenLabs TTS |
| F8 | Assembly | Stitch beats + captions + audio into a 9:16 MP4 (slideshow or montage) | `FFmpegCompositor`, `input_from` fan-in |
| F9 | Durable storage | Every asset + manifest to B2; optional Object Lock (immutable) | `S3StorageBackend.for_backblaze`, `ObjectStorageSink`, `ObjectLockConfig` |
| F10 | Provenance & verify | Lineage graph of the run; public "verify this asset" (hash check) | `Manifest.verify()`, CLI `verify`, `ParquetSink` for lineage queries |
| F11 | Live progress | Per-beat streaming status incl. "judged 0.6 → regenerating → passed" | `pipeline.stream()` / `loop.stream()` → SSE |
| F12 | Reliability | Model fallback + retries; crash-safe async video jobs | `fallback_models`, retry policy, `on_submit` checkpointing |

---

## 9. The Self-Healing Loop (core IP)

```text
beat prompt ──► generate visual (iter 0)
                     │
                     ▼
             VisionJudge.evaluate()  ── score dims: hook / text-legibility / artifacts / on-brand
                     │
          ┌── passed (≥ threshold) ──► keep beat
          │
          └── failed ──► refine prompt from feedback ──► regenerate (iter n)   [cap 1–2 iters]
                                    │
                                    ▼
                     parent_run_id links iter n → iter n-1  (lineage in manifest)
```

- Built on Genblaze `AgentLoop(build_pipeline, evaluator, max_iterations=…)`.
- `build_pipeline(ctx)` uses `ctx.last_evaluation.feedback` to rewrite the prompt each iteration.
- Judge is a **different model** than the generator (avoids "grading its own homework").
- Every attempt is a linked manifest; the reject→fix→pass chain is the demo money-shot and the
  literal embodiment of the hackathon's "generate, evaluate, retry, store" theme.
- **Cost-bounded:** `max_iterations` capped; `AgentResult.total_cost_usd` sums all iterations.

---

## 10. Provenance & Trust (differentiator)

- Each run emits a canonical-JSON **manifest** with a SHA-256 `canonical_hash`; `manifest.verify()`
  confirms integrity and that every output asset declares a valid `sha256`.
- Manifests + assets are uploaded to B2 by `ObjectStorageSink` (post-transfer hashes rebound into
  the manifest). Asset URLs are durable/credential-free.
- **Object Lock (GOVERNANCE default)** can retain manifests immutably — hash *proves* no tampering,
  Object Lock *prevents* it. (Bucket must be created with Object Lock enabled.)
- **Lineage:** `parent_run_id` chains iterations; `ParquetSink` makes lineage queryable for the
  in-app lineage graph.
- **Public verify view:** given an asset/run, fetch its manifest, recompute the hash, and display
  provider/model/prompt/params/timestamps + pass/fail history. Mirrors `genblaze verify`.

---

## 11. Providers (lean, GMI-credit-friendly)

| Role | Provider/model (primary) | Fallback | Notes |
|------|--------------------------|----------|-------|
| Beat script + vision judge | OpenAI (LLM + vision) | — | judge ≠ generator |
| Slide image (concept) | GMICloud `reve-create` ($0.007) / `gemini-2.5-flash-image` | DALL·E / gpt-image | cheapest first |
| Product image edit | GMICloud Bria (relight/genfill), FLUX Kontext, Seedream (`image_url`) | — | underused = differentiation |
| POV clip | GMICloud `pixverse-v5.6-i2v` ($0.03) / `seedance-fast` ($0.022) | Kling | image→clip via `external_inputs`/chain |
| Voiceover | ElevenLabs TTS | OpenAI TTS | optional; word-timings available |
| Music | Stability `stable-audio-2.5` | — | duration-driven |
| Assembly/captions | `FFmpegCompositor` / `FFmpegTransform` | — | local, deterministic |
| Storage/provenance | `genblaze-s3` (B2) | — | Object Lock + Parquet |

> Verify exact `pip install genblaze-*` extra names against the repo `pyproject` on Day 0.
> Register pricing strategies explicitly (0.3.0 ships zero hardcoded prices) so `cost_usd` populates.

---

## 12. Success Metrics

**Product**
- Slideshow: topic → finished 9:16 MP4 in B2 in < ~90s.
- ≥ 1 beat visibly caught and improved by the judge loop in a typical run.
- 100% of output assets verify (`manifest.verify() == True`).

**Hackathon**
- End-to-end autonomous loop demonstrated live (slideshow) + async (POV).
- B2 shown as system of record (manifests, lineage graph, Object Lock, verify view).
- Genblaze used as designed (multi-provider, fallback, streaming, provenance).
- Clear production path (async jobs, checkpoint/resume, moderation, cost tracking).

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AI garbles on-slide text | Generate clean background; burn captions with ffmpeg `overlay_text` + safe-zones; judge checks legibility |
| Video render too slow for live demo | Slideshow is the live path; POV pre-generated async with checkpoint/resume |
| Cross-beat visual inconsistency | Shared style seed + `image_url` conditioning; judge enforces on-brand |
| Provider outage mid-demo | `fallback_models` + retry policy; pre-baked showcase campaigns |
| Judge inflates scores (no retries fire) | Different judge model; rubric with anchored 1–5 sub-scores; seed one weak beat for the demo |
| Exact genblaze extras/model slugs drift | Verify against repo `pyproject` + `model-matrix.md` on Day 0; `suspected_dead` models exist in the matrix |
| Private-bucket URLs 403 in browser | Configure `public_url_base` (Cloudflare) or presign at read time |

---

## 14. Future Roadmap

- **Phase 1 (MVP):** faceless slideshow + POV montage, self-healing loop, B2 provenance.
- **Phase 2:** talking-creator UGC via a **custom Genblaze lip-sync adapter** (Sync.so / VEED Fabric / D-ID); more formats.
- **Phase 3:** A/B variant sets, performance signals, brand-kit/style memory.
- **Phase 4:** scheduled/continuous content generation; multi-tenant SaaS with Object-Lock audit trails as a paid feature.

---

## Product Positioning

> **A faceless short-form studio that generates TikTok slideshows and POV montages, automatically
> fixes its own weak frames, and proves how every asset was made — with durable, verifiable
> provenance on Backblaze B2.**
