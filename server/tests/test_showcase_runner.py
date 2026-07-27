from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from scripts.pregenerate_showcases import wait_for_campaign


class ShowcaseRunnerTests(unittest.TestCase):
    def test_polling_recovers_from_one_transient_transport_error(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ReadError("connection aborted", request=request)
            return httpx.Response(200, json={"status": "done"}, request=request)

        with httpx.Client(
            base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler)
        ) as client:
            with (
                patch("builtins.print") as report,
                patch("scripts.pregenerate_showcases.time.sleep") as sleep,
            ):
                campaign = wait_for_campaign(client, "job-1", poll_interval=0.01, timeout=1)

        self.assertEqual(campaign["status"], "done")
        self.assertEqual(calls, 2)
        sleep.assert_called_once_with(0.01)
        report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
