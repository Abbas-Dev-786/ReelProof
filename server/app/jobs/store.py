from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ..config import settings

DB_PATH = settings.database_file
_lock = threading.Lock()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id      TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'pending',
                topic       TEXT,
                mode        TEXT,
                beat_count  INTEGER NOT NULL DEFAULT 5,
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
                checkpoint_json TEXT,
                status        TEXT NOT NULL DEFAULT 'pending',
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (job_id, step_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS product_assets (
                asset_id      TEXT PRIMARY KEY,
                job_id        TEXT NOT NULL,
                filename      TEXT NOT NULL,
                media_type    TEXT NOT NULL,
                asset_url     TEXT NOT NULL,
                sha256        TEXT,
                run_id        TEXT NOT NULL,
                manifest_hash TEXT NOT NULL,
                manifest_uri  TEXT,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS provenance_records (
                run_id        TEXT PRIMARY KEY,
                job_id        TEXT,
                manifest_json TEXT NOT NULL,
                manifest_hash TEXT NOT NULL,
                manifest_uri  TEXT,
                parent_run_id TEXT,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_product_assets_job_id ON product_assets(job_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_provenance_records_job_id ON provenance_records(job_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_provenance_records_parent_run_id ON provenance_records(parent_run_id)"
        )

        # Lightweight migration for databases created before beat_count existed.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "beat_count" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN beat_count INTEGER NOT NULL DEFAULT 5")

        checkpoint_columns = {row[1] for row in conn.execute("PRAGMA table_info(checkpoints)")}
        if "checkpoint_json" not in checkpoint_columns:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN checkpoint_json TEXT")
        if "status" not in checkpoint_columns:
            conn.execute(
                "ALTER TABLE checkpoints ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
            )
        if "created_at" not in checkpoint_columns:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN created_at DATETIME")
        if "updated_at" not in checkpoint_columns:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN updated_at DATETIME")


def create_job(job_id: str, topic: str, mode: str, beat_count: int) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, status, topic, mode, beat_count) VALUES (?,?,?,?,?)",
            (job_id, "pending", topic, mode, beat_count),
        )


def set_running(job_id: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='running', updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
            (job_id,),
        )


def claim_job_start(job_id: str) -> bool:
    """Atomically transition a draft job to running exactly once."""
    with _lock, _conn() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs SET status='running', updated_at=CURRENT_TIMESTAMP
            WHERE job_id=? AND status='pending'
            """,
            (job_id,),
        )
    return cursor.rowcount == 1


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


def get_job(job_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("result_json"):
        try:
            d["result"] = json.loads(d["result_json"])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Job {job_id} has invalid persisted result JSON") from exc
    return d


def record_product_asset(
    *,
    asset_id: str,
    job_id: str,
    filename: str,
    media_type: str,
    asset_url: str,
    sha256: str | None,
    run_id: str,
    manifest_hash: str,
    manifest_uri: str | None,
) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO product_assets
                (asset_id, job_id, filename, media_type, asset_url, sha256, run_id, manifest_hash, manifest_uri)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                asset_id,
                job_id,
                filename,
                media_type,
                asset_url,
                sha256,
                run_id,
                manifest_hash,
                manifest_uri,
            ),
        )


def list_product_assets(job_id: str) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM product_assets WHERE job_id=? ORDER BY created_at, asset_id", (job_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def record_provenance(
    *,
    run_id: str,
    job_id: str | None,
    manifest_json: str,
    manifest_hash: str,
    manifest_uri: str | None,
    parent_run_id: str | None,
) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO provenance_records
                (run_id, job_id, manifest_json, manifest_hash, manifest_uri, parent_run_id)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET
                job_id=excluded.job_id,
                manifest_json=excluded.manifest_json,
                manifest_hash=excluded.manifest_hash,
                manifest_uri=excluded.manifest_uri,
                parent_run_id=excluded.parent_run_id
            """,
            (run_id, job_id, manifest_json, manifest_hash, manifest_uri, parent_run_id),
        )


def get_provenance(run_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM provenance_records WHERE run_id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def lineage_for_job(job_id: str) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT run_id, manifest_hash, manifest_uri, parent_run_id, created_at
            FROM provenance_records WHERE job_id=? ORDER BY created_at, run_id
            """,
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def lineage_for_run(run_id: str) -> list[dict[str, Any]]:
    """Follow parent links from a run to its oldest recorded ancestor."""
    lineage: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_run_id: str | None = run_id
    while current_run_id and current_run_id not in seen:
        seen.add(current_run_id)
        record = get_provenance(current_run_id)
        if record is None:
            break
        lineage.append(
            {
                key: record[key]
                for key in (
                    "run_id",
                    "manifest_hash",
                    "manifest_uri",
                    "parent_run_id",
                    "created_at",
                )
            }
        )
        current_run_id = record["parent_run_id"]
    return lineage


def save_checkpoint(
    job_id: str,
    step_id: str,
    prediction_id: Any,
    checkpoint: dict[str, Any] | None = None,
) -> None:
    """Persist an upstream prediction id immediately after provider submission.

    ``checkpoint`` contains the minimum public step inputs needed to resume
    polling after a process restart. It intentionally never stores credentials.
    """
    checkpoint_json = json.dumps(checkpoint, separators=(",", ":")) if checkpoint else None
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO checkpoints (job_id, step_id, prediction_id, checkpoint_json, status)
            VALUES (?,?,?,?, 'pending')
            ON CONFLICT(job_id, step_id) DO UPDATE SET
                prediction_id=excluded.prediction_id,
                checkpoint_json=excluded.checkpoint_json,
                status='pending',
                updated_at=CURRENT_TIMESTAMP
            """,
            (job_id, step_id, str(prediction_id), checkpoint_json),
        )


def complete_checkpoint(job_id: str, step_id: str) -> None:
    """Mark a checkpoint terminal after the provider has returned an asset."""
    with _lock, _conn() as conn:
        conn.execute(
            """
            UPDATE checkpoints SET status='completed', updated_at=CURRENT_TIMESTAMP
            WHERE job_id=? AND step_id=?
            """,
            (job_id, step_id),
        )


def pending_checkpoints(job_id: str) -> list[dict[str, Any]]:
    """Return resumable checkpoints in submission order, ignoring malformed records."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT job_id, step_id, prediction_id, checkpoint_json, created_at, updated_at
            FROM checkpoints
            WHERE job_id=? AND status='pending' AND checkpoint_json IS NOT NULL
            ORDER BY created_at, step_id
            """,
            (job_id,),
        ).fetchall()

    checkpoints: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["checkpoint_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        checkpoints.append({**dict(row), "checkpoint": payload})
    return checkpoints


def resumable_pov_jobs() -> list[dict[str, Any]]:
    """Return interrupted POV jobs that have at least one durable prediction."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT jobs.*
            FROM jobs
            JOIN checkpoints ON checkpoints.job_id = jobs.job_id
            WHERE jobs.status='running'
              AND jobs.mode='pov'
              AND checkpoints.status='pending'
              AND checkpoints.checkpoint_json IS NOT NULL
            ORDER BY jobs.created_at, jobs.job_id
            """
        ).fetchall()
    return [dict(row) for row in rows]
