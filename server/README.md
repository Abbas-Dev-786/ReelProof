# ReelProof API

The API creates and tracks short-form campaign generation jobs. It uses SQLite
for job state, GenBlaze for provenance-aware provider pipelines, and Backblaze
B2 for durable assets.

Campaign planning uses Z.ai's GLM-5.2 text flagship and frame evaluation uses
Qwen 3.5 397B, NVIDIA's hosted multimodal NIM model, through
`genblaze-nvidia`. Each call uses JSON-schema structured output, while local
validation remains the final trust boundary. Set `NVIDIA_API_KEY` for
NVIDIA's hosted NIM endpoint, or set `NVIDIA_CHAT_BASE_URL` to an
OpenAI-compatible self-hosted NIM endpoint. The default model IDs can be
overridden with `NVIDIA_PLANNER_MODEL` and `NVIDIA_VISION_MODEL`.

## Local setup

Use Python 3.11 or newer. Create `server/.env` from `.env.example`, then set
the credentials required for the provider paths you intend to run.

```bash
cd server
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m ruff check .
.venv/bin/python -m uvicorn main:app --reload --port 8000
```

The default smoke test is local-only. It validates configuration and required
executables without making paid provider calls:

```bash
.venv/bin/python smoke_test.py
```

`smoke_test.py --live` makes paid provider requests and should only be run with
an approved test account and B2 bucket.

## Demo showcases

Phase 7 includes a repeatable runner for the two slideshow and one POV showcase
campaigns. It creates real API jobs, waits for their verified B2-backed results,
and prints durable reel and manifest URLs for the demo runbook.

Before running it, ensure `ffmpeg` and `ffprobe` are on `PATH`, configure the
NVIDIA, GMI, Stability, and B2 credentials, and start the API in another shell.
This makes paid provider requests.

```bash
.venv/bin/python scripts/pregenerate_showcases.py
```

The API now uses bounded retry policies for images, audio, and video; image and
video fallback model lists are configurable with `GMI_IMAGE_FALLBACK_MODELS`,
`GMI_PRODUCT_IMAGE_FALLBACK_MODELS`, and `POV_VIDEO_FALLBACK_MODELS`. A shared
GenBlaze moderation hook screens prompts and asset outputs, while upload assets
are screened before they are ingested into B2.

Optional narration is controlled by `VOICEOVER_ENABLED`. When enabled, the
planner's non-empty `vo` beat lines are combined into one ElevenLabs narration
track, persisted with its own manifest, and mixed with the music bed. Both
slideshow and POV outputs use the same caption safe-zone; POV renders are also
run through the bounded visual-quality loop before assembly. Captioned frames,
music, narration, generated clips, and the final reel are persisted through
B2-backed GenBlaze runs and recorded in campaign provenance.

## Operational notes

- `jobs.db`, `output/`, and `data/` are local runtime state and are not committed.
- Campaign workers use renewable database leases. On startup, a worker whose
  lease expired is requeued, including interrupted slideshow and POV jobs.
  Progress events are stored in SQLite and replayed over SSE with
  `Last-Event-ID`, so reconnecting clients do not lose their campaign timeline.
- Product uploads are restricted to JPEG, PNG, and WebP; their byte and pixel
  limits are configured in `.env`.
- SQLite is suitable for a single-node deployment. For multiple hosts, point
  all replicas at a shared production database and replace the local worker
  threads with a managed queue before increasing concurrency.
- Set `B2_OBJECT_LOCK_ENABLED=true` only after enabling Object Lock on the B2
  bucket itself; a configuration flag cannot retrofit retention to an existing
  non-lockable bucket.
