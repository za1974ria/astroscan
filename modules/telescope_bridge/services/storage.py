"""Telescope Bridge — persistent storage for pairing & telemetry.

V1 minimal: 3 tables (tb_pair_tokens, tb_agents, tb_telemetry) in a
SEPARATE sqlite file from the main AstroScan DB. Path:
    <ASTROSCAN_DATA_DIR>/telescope_bridge.db

This module is the ONLY place inside `modules.telescope_bridge` that
touches sqlite. The module-level read-only hardware posture remains:
nothing here issues motion/control commands — it only persists pairing
records and append-only telemetry.

Concurrency: each function opens a short-lived connection. SQLite WAL
mode handles concurrent Gunicorn workers; per-request transactions
keep pair-token consumption atomic (`UPDATE … WHERE consumed=0` is
single-statement and serialized by SQLite's writer lock).
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from app.services.paths import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "telescope_bridge.db")

PAIR_TOKEN_TTL_SECONDS = 300
TELEMETRY_PAYLOAD_MAX_BYTES = 64 * 1024

_init_lock = threading.Lock()
_initialized = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Idempotent. Safe to call from every request; the lock guard plus
    `_initialized` flag ensure exactly-once schema creation per process."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tb_pair_tokens (
                    token       TEXT PRIMARY KEY,
                    label       TEXT,
                    created_at  TEXT NOT NULL,
                    expires_at  INTEGER NOT NULL,
                    consumed    INTEGER NOT NULL DEFAULT 0,
                    consumed_by TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_pair_expires
                    ON tb_pair_tokens(expires_at);

                CREATE TABLE IF NOT EXISTS tb_agents (
                    agent_id     TEXT PRIMARY KEY,
                    label        TEXT,
                    devices_json TEXT,
                    paired_at    TEXT NOT NULL,
                    last_seen_at TEXT
                );

                CREATE TABLE IF NOT EXISTS tb_telemetry (
                    sample_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id     TEXT NOT NULL,
                    ingested_at  TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_telemetry_agent_ts
                    ON tb_telemetry(agent_id, ingested_at DESC);
                """
            )
        _initialized = True


def _purge_expired_tokens(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM tb_pair_tokens WHERE consumed=1 OR expires_at < ?",
        (_now_epoch(),),
    )


# ── Pairing tokens ───────────────────────────────────────────────────


def create_pair_token(label: str | None) -> dict:
    """Generate, persist, return a fresh single-use pairing token."""
    init_db()
    token = secrets.token_urlsafe(32)
    expires_at = _now_epoch() + PAIR_TOKEN_TTL_SECONDS
    safe_label = (label or "")[:128] if isinstance(label, str) else ""
    with _connect() as conn:
        _purge_expired_tokens(conn)
        conn.execute(
            "INSERT INTO tb_pair_tokens(token, label, created_at, expires_at, consumed) "
            "VALUES (?, ?, ?, ?, 0)",
            (token, safe_label, _now_iso(), expires_at),
        )
    return {
        "pairing_token": token,
        "expires_in_seconds": PAIR_TOKEN_TTL_SECONDS,
        "label": safe_label,
    }


def consume_pair_token(token: str, agent_id: str) -> tuple[bool, str]:
    """Atomic single-use consumption.

    Returns (ok, reason). reason ∈ {"ok", "not_found", "expired",
    "already_consumed", "invalid"}.
    """
    init_db()
    if not isinstance(token, str) or not token:
        return False, "invalid"
    with _connect() as conn:
        row = conn.execute(
            "SELECT expires_at, consumed FROM tb_pair_tokens WHERE token=?",
            (token,),
        ).fetchone()
        if row is None:
            return False, "not_found"
        if int(row["consumed"]) == 1:
            return False, "already_consumed"
        if int(row["expires_at"]) < _now_epoch():
            return False, "expired"
        # Atomic transition: UPDATE only if still consumed=0.
        cur = conn.execute(
            "UPDATE tb_pair_tokens SET consumed=1, consumed_by=? "
            "WHERE token=? AND consumed=0",
            (agent_id, token),
        )
        if cur.rowcount != 1:
            return False, "already_consumed"
    return True, "ok"


# ── Agents ───────────────────────────────────────────────────────────


def register_agent(agent_id: str, label: str | None, devices: list) -> None:
    """Upsert agent record. Caller validates agent_id non-empty."""
    init_db()
    devices_json = json.dumps(devices or [], ensure_ascii=False, default=str)
    if len(devices_json) > TELEMETRY_PAYLOAD_MAX_BYTES:
        devices_json = "[]"
    with _connect() as conn:
        conn.execute(
            "INSERT INTO tb_agents(agent_id, label, devices_json, paired_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(agent_id) DO UPDATE SET "
            "  label=excluded.label, devices_json=excluded.devices_json, "
            "  last_seen_at=excluded.last_seen_at",
            (agent_id, (label or "")[:128], devices_json, _now_iso(), _now_iso()),
        )


def list_agents() -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT agent_id, label, devices_json, paired_at, last_seen_at "
            "FROM tb_agents ORDER BY paired_at DESC"
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        try:
            devices = json.loads(r["devices_json"] or "[]")
        except (TypeError, ValueError):
            devices = []
        out.append({
            "agent_id": r["agent_id"],
            "label": r["label"],
            "devices": devices,
            "paired_at": r["paired_at"],
            "last_seen_at": r["last_seen_at"],
        })
    return out


def agent_exists(agent_id: str) -> bool:
    init_db()
    if not isinstance(agent_id, str) or not agent_id:
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM tb_agents WHERE agent_id=?", (agent_id,)
        ).fetchone()
    return row is not None


def touch_agent(agent_id: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE tb_agents SET last_seen_at=? WHERE agent_id=?",
            (_now_iso(), agent_id),
        )


# ── Telemetry ────────────────────────────────────────────────────────


def store_telemetry(agent_id: str, telemetry: Any) -> dict:
    """Append-only persistence of a telemetry sample. Payload is
    serialized to JSON and capped at TELEMETRY_PAYLOAD_MAX_BYTES."""
    init_db()
    try:
        payload_json = json.dumps(telemetry, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        payload_json = "{}"
    if len(payload_json) > TELEMETRY_PAYLOAD_MAX_BYTES:
        payload_json = json.dumps(
            {"error": "payload too large",
             "size_bytes": len(payload_json),
             "limit_bytes": TELEMETRY_PAYLOAD_MAX_BYTES},
            ensure_ascii=False,
        )
    ts = _now_iso()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO tb_telemetry(agent_id, ingested_at, payload_json) "
            "VALUES (?, ?, ?)",
            (agent_id, ts, payload_json),
        )
        conn.execute(
            "UPDATE tb_agents SET last_seen_at=? WHERE agent_id=?",
            (ts, agent_id),
        )
    return {"ingested_at": ts, "bytes": len(payload_json)}
