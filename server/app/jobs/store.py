from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path("jobs.db")
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id      TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'pending',
                topic       TEXT,
                mode        TEXT,
                result_json TEXT,
                error       TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                job_id        TEXT,
                step_id       TEXT,
                prediction_id TEXT,
                PRIMARY KEY (job_id, step_id)
            )
        """)


def create_job(job_id: str, topic: str, mode: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, status, topic, mode) VALUES (?,?,?,?)",
            (job_id, "pending", topic, mode),
        )


def set_running(job_id: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='running', updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
            (job_id,),
        )


def set_result(job_id: str, result_json: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='done', result_json=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
            (result_json, job_id),
        )


def set_failed(job_id: str, error: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
            (error, job_id),
        )


def get_job(job_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("result_json"):
        d["result"] = json.loads(d["result_json"])
    return d


def save_checkpoint(job_id: str, step_id: str, prediction_id: Any) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO checkpoints (job_id, step_id, prediction_id) VALUES (?,?,?)",
            (job_id, step_id, str(prediction_id)),
        )
