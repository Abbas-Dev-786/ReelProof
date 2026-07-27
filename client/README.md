# ReelProof client

The React client talks directly to the ReelProof FastAPI service. Set the API URL before starting a development or production build:

```dotenv
VITE_API_URL=http://localhost:8000
```

Copy the value into `client/.env` for local development. Vite embeds `VITE_API_URL` during the build, so set it to the deployed API origin in each production environment.

Start the API on port `8000`, then run the client from this directory with `pnpm dev`. The default FastAPI CORS configuration permits the Vite development origin (`http://localhost:5173`).

## API coverage

| API endpoint | Client behavior |
| --- | --- |
| `GET /health` | Shows the live API connection state in the header and rechecks it every 30 seconds. |
| `POST /campaigns` | Creates a campaign before generation begins. |
| `POST /campaigns/{job_id}/assets` | Uploads each selected product image before starting a draft campaign. |
| `POST /campaigns/{job_id}/start` | Starts a campaign after all product uploads succeed. |
| `GET /campaigns/{job_id}/stream` | Streams durable generation progress to the activity panel. |
| `GET /campaigns/{job_id}` | Reconciles campaign status and final output; it also polls as a fallback if the stream reconnects. |
| `GET /campaigns/{job_id}/package` | Displays the durable campaign package, manifest, and uploaded product assets. |
| `GET /campaigns/{job_id}/lineage` | Displays campaign-wide retained generation lineage. |
| `GET /verify/{run_id}` | Verifies a manifest in the campaign result and public verification workspace. |

The client never retries a mutation automatically, so a network interruption cannot accidentally create a duplicate paid generation. Read requests use React Query caching and controlled refreshes to keep a long-running campaign current.
