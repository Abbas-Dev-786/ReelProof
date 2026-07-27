# Showcase polling transport recovery

## DEBUG REPORT

- **Symptom:** On Windows, `scripts/pregenerate_showcases.py` created the
  morning-coffee campaign, then failed during `GET /campaigns/{job_id}` with
  `httpx.ReadError: [WinError 10053]`.
- **Root cause:** The showcase runner treated every `httpx.TransportError` in
  its idempotent status-polling GET as fatal. A locally aborted/restarted HTTP
  connection therefore terminated the runner before it could read the durable
  SQLite job state.
- **Fix:** `wait_for_campaign()` retries only transport failures from its GET
  until the existing campaign deadline, reports the transient error, and keeps
  POST creation non-retried to avoid duplicate paid jobs. It now prints the
  job ID as soon as creation succeeds. The README directs long-running
  showcases to use Uvicorn without `--reload`, since reload can terminate the
  in-process worker.
- **Evidence:** Before the change, a regression test that made a real
  `httpx.Client` raise one `ReadError` failed immediately. After the change it
  polls a second time and returns the `done` response.
- **Regression test:** `server/tests/test_showcase_runner.py`.
- **Related:** The API uses in-process worker threads. If Windows keeps
  aborting every connection or the Uvicorn process exits, the runner will
  retry safely but cannot restore a server that remains down; inspect the
  Uvicorn console and host security logs in that case.
- **Status:** DONE_WITH_CONCERNS — the runner recovery is verified; the exact
  host-level cause of the single Windows socket abort cannot be established
  without the server-side console output.
