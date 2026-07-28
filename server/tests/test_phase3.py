from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.jobs import store
from main import app


def _one_pixel_png() -> bytes:
    image = Image.new("RGB", (1, 1), "white")
    data = BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


ONE_PIXEL_PNG = _one_pixel_png()


class Phase3ApiTests(unittest.TestCase):
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

    def create_draft(self) -> str:
        response = self.client.post(
            "/campaigns",
            json={"topic": "A quiet coffee ritual", "beat_count": 3, "start_immediately": False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
        return response.json()["job_id"]

    def test_create_campaign_can_disable_background_music(self) -> None:
        response = self.client.post(
            "/campaigns",
            json={
                "topic": "A quiet coffee ritual",
                "beat_count": 3,
                "generate_music": False,
                "start_immediately": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job_id"]
        self.assertEqual(store.get_job(job_id)["generate_music"], 0)

        campaign = self.client.get(f"/campaigns/{job_id}")
        self.assertEqual(campaign.status_code, 200)
        self.assertFalse(campaign.json()["generate_music"])

    def test_completed_campaign_returns_browser_readable_asset_urls(self) -> None:
        store.create_job("job-complete", "A quiet coffee ritual", "slideshow", 3)
        durable_urls = {
            "image": "https://cdn.example.test/reelproof/frame.png",
            "captioned": "https://cdn.example.test/reelproof/captioned.png",
            "reel": "https://cdn.example.test/reelproof/final.mp4",
            "music": "https://cdn.example.test/reelproof/music.mp3",
            "manifest": "https://cdn.example.test/reelproof/manifest.json",
        }
        result = {
            "job_id": "job-complete",
            "topic": "A quiet coffee ritual",
            "mode": "slideshow",
            "status": "done",
            "generate_music": True,
            "beats": [
                {
                    "index": 0,
                    "image_url": durable_urls["image"],
                    "captioned_url": durable_urls["captioned"],
                    "judge_iterations": 1,
                    "passed": True,
                }
            ],
            "reel_url": durable_urls["reel"],
            "music_url": durable_urls["music"],
            "manifest_uri": durable_urls["manifest"],
            "hashtags": [],
        }
        store.set_result("job-complete", json.dumps(result))

        def sign(url: str) -> str:
            return f"{url}?signed=browser"

        with patch("app.api.routes.browser_asset_url", side_effect=sign) as signer:
            response = self.client.get("/campaigns/job-complete")

        self.assertEqual(response.status_code, 200)
        campaign = response.json()
        self.assertEqual(campaign["beats"][0]["image_url"], f'{durable_urls["image"]}?signed=browser')
        self.assertEqual(
            campaign["beats"][0]["captioned_url"],
            f'{durable_urls["captioned"]}?signed=browser',
        )
        self.assertEqual(campaign["reel_url"], f'{durable_urls["reel"]}?signed=browser')
        self.assertEqual(campaign["music_url"], f'{durable_urls["music"]}?signed=browser')
        self.assertEqual(
            campaign["manifest_uri"], f'{durable_urls["manifest"]}?signed=browser'
        )
        self.assertEqual(signer.call_count, 5)

        persisted = store.get_job("job-complete")["result"]
        self.assertEqual(persisted["reel_url"], durable_urls["reel"])

    def test_campaign_package_returns_readable_uploaded_assets_and_manifests(self) -> None:
        store.create_job("job-package", "A quiet coffee ritual", "slideshow", 3)
        store.record_product_asset(
            asset_id="asset-1",
            job_id="job-package",
            filename="product.png",
            media_type="image/png",
            asset_url="https://cdn.example.test/reelproof/product.png",
            sha256="a" * 64,
            run_id="run-1",
            manifest_hash="b" * 64,
            manifest_uri="https://cdn.example.test/reelproof/product-manifest.json",
        )
        store.record_provenance(
            run_id="run-1",
            job_id="job-package",
            manifest_json="{}",
            manifest_hash="b" * 64,
            manifest_uri="https://cdn.example.test/reelproof/product-manifest.json",
            parent_run_id=None,
        )

        def sign(url: str) -> str:
            return f"{url}?signed=browser"

        with patch("app.api.routes.browser_asset_url", side_effect=sign):
            response = self.client.get("/campaigns/job-package/package")

        self.assertEqual(response.status_code, 200)
        package = response.json()
        self.assertEqual(
            package["product_assets"][0]["asset_url"],
            "https://cdn.example.test/reelproof/product.png?signed=browser",
        )
        self.assertEqual(
            package["product_assets"][0]["manifest_uri"],
            "https://cdn.example.test/reelproof/product-manifest.json?signed=browser",
        )
        self.assertEqual(
            package["provenance"][0]["manifest_uri"],
            "https://cdn.example.test/reelproof/product-manifest.json?signed=browser",
        )
        self.assertEqual(
            store.list_product_assets("job-package")[0]["asset_url"],
            "https://cdn.example.test/reelproof/product.png",
        )

    def test_rejects_non_image_product_upload(self) -> None:
        job_id = self.create_draft()
        response = self.client.post(
            f"/campaigns/{job_id}/assets",
            files={"file": ("notes.txt", b"not an image", "text/plain")},
        )
        self.assertEqual(response.status_code, 415)

    def test_ingests_product_upload_records_provenance_and_lineage(self) -> None:
        job_id = self.create_draft()
        ingested = {
            "asset_id": "asset-1",
            "asset_url": "https://example.test/product.png",
            "sha256": "a" * 64,
            "run_id": "run-1",
            "manifest_hash": "b" * 64,
            "manifest_uri": "https://example.test/manifest.json",
            "manifest_json": '{"schema_version":"1.0","run":null,"canonical_hash":"x"}',
            "parent_run_id": None,
        }
        staged_paths: list[Path] = []

        def capture_ingest(**kwargs):
            staged_path = kwargs["local_path"]
            self.assertTrue(staged_path.is_file())
            staged_paths.append(staged_path)
            return ingested

        with patch("app.api.routes.ingest_product_image", side_effect=capture_ingest):
            response = self.client.post(
                f"/campaigns/{job_id}/assets",
                files={"file": ("product.png", ONE_PIXEL_PNG, "image/png")},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(staged_paths), 1)
        self.assertTrue(staged_paths[0].is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertFalse(staged_paths[0].exists())
        self.assertEqual(response.json()["run_id"], "run-1")
        self.assertEqual(len(store.list_product_assets(job_id)), 1)
        self.assertEqual(store.get_provenance("run-1")["manifest_hash"], "b" * 64)

        lineage = self.client.get(f"/campaigns/{job_id}/lineage")
        self.assertEqual(lineage.status_code, 200)
        self.assertEqual(lineage.json()["runs"][0]["run_id"], "run-1")

        package = self.client.get(f"/campaigns/{job_id}/package")
        self.assertEqual(package.status_code, 200)
        self.assertEqual(package.json()["product_assets"][0]["asset_id"], "asset-1")

    def test_rejects_image_content_type_with_non_image_payload(self) -> None:
        job_id = self.create_draft()
        response = self.client.post(
            f"/campaigns/{job_id}/assets",
            files={"file": ("fake.png", b"not actually an image", "image/png")},
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_unknown_create_campaign_fields(self) -> None:
        response = self.client.post(
            "/campaigns",
            json={"topic": "A quiet coffee ritual", "unexpected": "value"},
        )
        self.assertEqual(response.status_code, 422)

    def test_starting_draft_launches_worker_once(self) -> None:
        job_id = self.create_draft()
        with patch("app.api.routes.launch_worker") as launch_worker:
            response = self.client.post(f"/campaigns/{job_id}/start")
            repeated = self.client.post(f"/campaigns/{job_id}/start")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repeated.status_code, 409)
        launch_worker.assert_called_once()

    def test_starting_draft_passes_generate_music_to_worker(self) -> None:
        response = self.client.post(
            "/campaigns",
            json={
                "topic": "A quiet coffee ritual",
                "beat_count": 3,
                "generate_music": False,
                "start_immediately": False,
            },
        )
        job_id = response.json()["job_id"]

        with patch("app.api.routes.launch_worker") as launch_worker:
            start = self.client.post(f"/campaigns/{job_id}/start")

        self.assertEqual(start.status_code, 200)
        self.assertIs(launch_worker.call_args.kwargs["generate_music"], False)

    def test_verify_uses_persisted_provenance_record(self) -> None:
        store.record_provenance(
            run_id="run-verify",
            job_id=None,
            manifest_json="{}",
            manifest_hash="c" * 64,
            manifest_uri="https://example.test/manifest.json",
            parent_run_id=None,
        )
        with patch(
            "app.api.routes.verify_manifest_json",
            return_value={
                "verified": True,
                "manifest_hash": "c" * 64,
                "provider": "ingest",
                "model": "product-upload",
                "created_at": "2026-07-23T00:00:00+00:00",
            },
        ):
            response = self.client.get("/verify/run-verify")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["verified"])
        self.assertEqual(response.json()["lineage"][0]["run_id"], "run-verify")


if __name__ == "__main__":
    unittest.main()
