# ReelProof API

The API creates and tracks short-form campaign generation jobs. It uses SQLite
for job state, GenBlaze for provenance-aware provider pipelines, and Backblaze
B2 for durable assets.

Campaign planning defaults to Groq's `openai/gpt-oss-20b` with strict
JSON-schema output. After its bounded retry budget is exhausted for a transient
provider failure, it fails over to `openai/gpt-oss-120b` using the same strict
schema. Rendered-frame evaluation uses Groq's multimodal `qwen/qwen3.6-27b`
with JSON Object mode; local Pydantic validation remains its final semantic
trust boundary. Set `GROQ_API_KEY` and `LLM_PROVIDER=groq`. Every request has
an explicit timeout, retry cap, and `429`/`Retry-After` handling. Set
`LLM_PROVIDER=nvidia` with `NVIDIA_API_KEY` to use the retained NIM fallback;
model IDs can be overridden with the provider-specific `*_PLANNER_MODEL`,
`GROQ_PLANNER_FALLBACK_MODEL`, and `*_VISION_MODEL` settings.

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

`smoke_test.py --live` makes paid image and music requests and should only be
run with an approved test account and B2 bucket. Full campaign creation also
requires a browser-reachable `B2_PUBLIC_URL_BASE` until presigned asset URLs
are implemented.

## LangSmith observability

Set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and optionally
`LANGSMITH_PROJECT=reelproof` to trace campaign roots, each Groq attempt
(including model, provider, latency, and retry number), and every GenBlaze
image, audio, and video pipeline. Traces contain prompts and generated asset
URLs; use only an approved LangSmith workspace. The feature is fail-open: an
unavailable LangSmith backend never fails a campaign. Query recent runs with:

```bash
langsmith trace list --project reelproof --limit 10 --show-hierarchy
```

## Demo showcases

Phase 7 includes a repeatable runner for the two slideshow and one POV showcase
campaigns. It creates real API jobs, waits for their verified B2-backed results,
and prints durable reel and manifest URLs for the demo runbook.

Before running it, ensure `ffmpeg` and `ffprobe` are on `PATH`, configure the
selected LLM provider, GMI, Stability, and B2 credentials, and start the API
in another shell **without** `--reload`. Reload mode is for development only:
when source files change it terminates the server process and its in-process
campaign worker, which interrupts a showcase run.
This makes paid provider requests.

```bash
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
.venv/bin/python scripts/pregenerate_showcases.py
```

In an activated Windows virtual environment, use the equivalent commands:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
python .\scripts\pregenerate_showcases.py
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
