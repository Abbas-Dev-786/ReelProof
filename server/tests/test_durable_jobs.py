from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.jobs import store
from main import app


class DurableJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = store.DB_PATH
        store.DB_PATH = Path(self.temp_dir.name) / "jobs.db"
        store.init_db()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        store.DB_PATH = self.previous_db_path
        self.temp_dir.cleanup()

    def test_job_lease_prevents_duplicate_workers_and_recovers_expired_work(self) -> None:
        store.create_job("job-1", "A calm coffee ritual", "slideshow", 3)
        self.assertTrue(store.claim_job_start("job-1", "worker-a", 60))
        self.assertFalse(store.claim_job_start("job-1", "worker-b", 60))
        self.assertFalse(store.renew_job_lease("job-1", "worker-b", 60))
        self.assertTrue(store.renew_job_lease("job-1", "worker-a", 60))

        with store._conn() as conn:  # type: ignore[attr-defined]
            conn.execute(
                "UPDATE jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id='job-1'"
            )

        self.assertEqual(store.requeue_expired_jobs(), 1)
        self.assertEqual([job["job_id"] for job in store.recoverable_jobs()], ["job-1"])

    def test_stream_replays_persisted_events_for_any_connected_client(self) -> None:
        store.create_job("job-stream", "A calm coffee ritual", "slideshow", 3)
        first_id = store.append_event("job-stream", "engine.started", {"job_id": "job-stream"})
        second_id = store.append_event("job-stream", "beat.completed", {"beat_index": 0})
        store.set_failed("job-stream", "intentional test completion")

        response = self.client.get("/campaigns/job-stream/stream")

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"id: {first_id}", response.text)
        self.assertIn(f"id: {second_id}", response.text)
        self.assertIn('"type":"beat.completed"', response.text)
        self.assertIn("event: done", response.text)


if __name__ == "__main__":
    unittest.main()
