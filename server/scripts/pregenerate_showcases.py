#!/usr/bin/env python3
"""Create the three demo-safe ReelProof showcase campaigns through the API.

Run this only after the API, provider credentials, B2, and ffmpeg are configured.
The script intentionally uses the public campaign API so completed jobs retain the
same B2 manifests, provenance, and checkpoint behaviour as a user-created run.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, cast

import httpx


@dataclass(frozen=True)
class Showcase:
    name: str
    topic: str
    mode: str
    beat_count: int


SHOWCASES = (
    Showcase(
        name="morning-coffee-slideshow",
        topic="A quiet morning coffee ritual for people who want less screen time",
        mode="slideshow",
        beat_count=4,
    ),
    Showcase(
        name="desk-reset-slideshow",
        topic="A calming five-minute desk reset before deep work",
        mode="slideshow",
        beat_count=4,
    ),
    Showcase(
        name="weekend-walk-pov",
        topic="A slow weekend neighborhood walk that makes ordinary moments feel cinematic",
        mode="pov",
        beat_count=3,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("REELPROOF_API_URL", "http://127.0.0.1:8000"),
        help="Running ReelProof API URL (default: %(default)s)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between status checks (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1_800.0,
        help="Maximum seconds to wait for each campaign (default: %(default)s)",
    )
    return parser.parse_args()


def create_showcase(client: httpx.Client, showcase: Showcase) -> str:
    response = client.post(
        "/campaigns",
        json={
            "topic": showcase.topic,
            "mode": showcase.mode,
            "beat_count": showcase.beat_count,
            "start_immediately": True,
        },
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    return str(payload["job_id"])


def wait_for_campaign(
    client: httpx.Client, job_id: str, *, poll_interval: float, timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/campaigns/{job_id}")
        response.raise_for_status()
        campaign = cast(dict[str, Any], response.json())
        if campaign["status"] == "done":
            return campaign
        if campaign["status"] == "failed":
            raise RuntimeError(campaign.get("error") or f"Campaign {job_id} failed")
        time.sleep(poll_interval)
    raise TimeoutError(f"Campaign {job_id} did not complete within {timeout:.0f} seconds")


def main() -> int:
    args = parse_args()
    if args.poll_interval <= 0 or args.timeout <= 0:
        raise ValueError("--poll-interval and --timeout must be greater than zero")

    completed: list[dict[str, str]] = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        health = client.get("/health")
        health.raise_for_status()
        for showcase in SHOWCASES:
            print(f"Starting {showcase.name} ({showcase.mode})…", flush=True)
            job_id = create_showcase(client, showcase)
            campaign = wait_for_campaign(
                client,
                job_id,
                poll_interval=args.poll_interval,
                timeout=args.timeout,
            )
            completed.append(
                {
                    "name": showcase.name,
                    "job_id": job_id,
                    "run_id": str(campaign["run_id"]),
                    "reel_url": str(campaign["reel_url"]),
                    "manifest_uri": str(campaign["manifest_uri"]),
                }
            )
            print(f"Completed {showcase.name}: {campaign['reel_url']}", flush=True)

    print(json.dumps({"showcases": completed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
