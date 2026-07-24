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

## Operational notes

- `jobs.db`, `output/`, and `data/` are local runtime state and are not committed.
- Product uploads are restricted to JPEG, PNG, and WebP; their byte and pixel
  limits are configured in `.env`.
- SQLite is suitable for a single API process. Move jobs and event delivery to a
  shared database and queue before running multiple API replicas.
