"""SQLite store for Sentinel — two tables, both auto-created.

Schema is minimal-but-complete: telemetry is overwritten in place;
audit events are append-only; neither table is ever exposed to anyone
outside the session via its tokens.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional

_DEFAULT_DB = "/root/astro_scan/data/archive_stellaire.db"
_SCHEMA_INITIALIZED = False


def _db_path() -> str:
    return os.environ.get("DB_PATH", _DEFAULT_DB)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 3000")
    return conn


def init_schema() -> None:
    global _SCHEMA_INITIALIZED
    if _SCHEMA_INITIALIZED:
        return
    with _connect() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS sentinel_sessions (
                session_id          TEXT PRIMARY KEY,
                parent_token        TEXT NOT NULL,
                driver_token        TEXT NOT NULL,
                driver_label        TEXT,
                state               TEXT NOT NULL,
                speed_limit_kmh     INTEGER NOT NULL,
                ttl_seconds         INTEGER NOT NULL,
                created_at          INTEGER NOT NULL,
                started_at          INTEGER,
                expires_at          INTEGER NOT NULL,
                ended_at            INTEGER,
                driver_consent_at   INTEGER,
                safe_zone_lat       REAL,
                safe_zone_lon       REAL,
                safe_zone_radius_m  INTEGER,
                last_lat            REAL,
                last_lon            REAL,
                last_accuracy       REAL,
                last_signal         TEXT,
                last_speed_kmh      REAL,
                last_heading_deg    REAL,
                last_battery_pct    INTEGER,
                last_update_at      INTEGER,
                max_speed_kmh       REAL NOT NULL DEFAULT 0,
                avg_speed_sum       REAL NOT NULL DEFAULT 0,
                avg_speed_samples   INTEGER NOT NULL DEFAULT 0,
                updates_count       INTEGER NOT NULL DEFAULT 0,
                over_speed_active   INTEGER NOT NULL DEFAULT 0,
                over_speed_streak_start INTEGER,
                safe_zone_exit_active INTEGER NOT NULL DEFAULT 0,
                safe_zone_outside_start INTEGER,
                signal_lost_active  INTEGER NOT NULL DEFAULT 0,
                low_battery_fired   INTEGER NOT NULL DEFAULT 0,
                sos_active          INTEGER NOT NULL DEFAULT 0,
                sos_triggered_at    INTEGER,
                sos_ack_at          INTEGER,
                stop_requested_by   TEXT,
                stop_requested_at   INTEGER,
                parent_fcm_token    TEXT,
                driver_fcm_token    TEXT,
                parent_platform     TEXT,
                driver_platform     TEXT
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_sentinel_expires "
            "ON sentinel_sessions(expires_at)"
        )
        # Idempotent ALTERs for already-existing tables (Phase A push delta).
        existing = {r["name"] for r in c.execute(
            "PRAGMA table_info(sentinel_sessions)"
        ).fetchall()}
        for col in ("parent_fcm_token", "driver_fcm_token",
                    "parent_platform", "driver_platform"):
            if col not in existing:
                c.execute(
                    f"ALTER TABLE sentinel_sessions ADD COLUMN {col} TEXT"
                )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS sentinel_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL,
                event_type      TEXT NOT NULL,
                payload_json    TEXT,
                created_at      INTEGER NOT NULL
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_sentinel_events_sid "
            "ON sentinel_events(session_id, created_at)"
        )
        # Zero-knowledge GeoIP aggregate. No IP, no session link, no precise time.
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS sentinel_country_counters (
                country_iso2    TEXT PRIMARY KEY,
                count           INTEGER NOT NULL DEFAULT 0,
                first_seen_day  TEXT NOT NULL,
                last_seen_day   TEXT NOT NULL
            )
            """
        )
    _SCHEMA_INITIALIZED = True


def insert_session(row: dict) -> None:
    init_schema()
    with _connect() as c:
        c.execute(
            """
            INSERT INTO sentinel_sessions
                (session_id, parent_token, driver_token, driver_label,
                 state, speed_limit_kmh, ttl_seconds,
                 created_at, expires_at,
                 safe_zone_lat, safe_zone_lon, safe_zone_radius_m)
            VALUES (?, ?, ?, ?, 'PENDING_DRIVER', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["session_id"], row["parent_token"], row["driver_token"],
                row["driver_label"],
                row["speed_limit_kmh"], row["ttl_seconds"],
                row["created_at"], row["expires_at"],
                row["safe_zone_lat"], row["safe_zone_lon"], row["safe_zone_radius_m"],
            ),
        )


def get_session(session_id: str) -> Optional[dict]:
    init_schema()
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM sentinel_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def mark_accepted(session_id: str) -> bool:
    init_schema()
    now = int(time.time())
    with _connect() as c:
        cur = c.execute(
            "UPDATE sentinel_sessions SET state = 'ACTIVE', "
            "started_at = ?, driver_consent_at = ? "
            "WHERE session_id = ? AND state = 'PENDING_DRIVER'",
            (now, now, session_id),
        )
        return cur.rowcount > 0


def write_telemetry(
    session_id: str,
    pos: dict,
    signal_label: str,
    new_max: float,
    new_avg_sum: float,
    new_avg_n: int,
    over_speed_active: bool,
    over_speed_streak_start: int | None,
    safe_zone_exit_active: bool,
    safe_zone_outside_start: int | None,
) -> None:
    init_schema()
    now = int(time.time())
    with _connect() as c:
        c.execute(
            """
            UPDATE sentinel_sessions
            SET last_lat = ?, last_lon = ?, last_accuracy = ?, last_signal = ?,
                last_speed_kmh = ?, last_heading_deg = ?,
                last_battery_pct = ?, last_update_at = ?,
                max_speed_kmh = ?, avg_speed_sum = ?, avg_speed_samples = ?,
                updates_count = updates_count + 1,
                over_speed_active = ?, over_speed_streak_start = ?,
                safe_zone_exit_active = ?, safe_zone_outside_start = ?,
                signal_lost_active = 0
            WHERE session_id = ?
            """,
            (
                pos["lat"], pos["lon"], pos["accuracy"], signal_label,
                pos["speed_kmh"], pos["heading_deg"],
                pos["battery_pct"], now,
                new_max, new_avg_sum, new_avg_n,
                1 if over_speed_active else 0, over_speed_streak_start,
                1 if safe_zone_exit_active else 0, safe_zone_outside_start,
                session_id,
            ),
        )


def trigger_sos(session_id: str) -> bool:
    init_schema()
    now = int(time.time())
    with _connect() as c:
        cur = c.execute(
            "UPDATE sentinel_sessions SET sos_active = 1, "
            "sos_triggered_at = ?, sos_ack_at = NULL "
            "WHERE session_id = ? AND sos_active = 0",
            (now, session_id),
        )
        return cur.rowcount > 0


def ack_sos(session_id: str) -> bool:
    init_schema()
    now = int(time.time())
    with _connect() as c:
        cur = c.execute(
            "UPDATE sentinel_sessions SET sos_ack_at = ? "
            "WHERE session_id = ? AND sos_active = 1 AND sos_ack_at IS NULL",
            (now, session_id),
        )
        return cur.rowcount > 0


def request_stop(session_id: str, requester: str, new_state: str) -> bool:
    init_schema()
    now = int(time.time())
    with _connect() as c:
        cur = c.execute(
            "UPDATE sentinel_sessions SET state = ?, "
            "stop_requested_by = ?, stop_requested_at = ? "
            "WHERE session_id = ? AND state = 'ACTIVE'",
            (new_state, requester, now, session_id),
        )
        return cur.rowcount > 0


def approve_stop(session_id: str, approver: str) -> tuple[bool, str | None]:
    """Approve a pending stop only by the counter-party.

    Returns (changed, reason_if_not_changed).
    """
    init_schema()
    now = int(time.time())
    with _connect() as c:
        row = c.execute(
            "SELECT state, stop_requested_by FROM sentinel_sessions "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return False, "not_found"
        if row["state"] not in ("STOP_PENDING_PARENT", "STOP_PENDING_DRIVER"):
            return False, "no_pending_stop"
        if row["stop_requested_by"] is None:
            return False, "no_requester"
        if row["stop_requested_by"] == approver:
            return False, "cannot_approve_own_request"
        cur = c.execute(
            "UPDATE sentinel_sessions SET state = 'ENDED', ended_at = ? "
            "WHERE session_id = ? AND state IN "
            "('STOP_PENDING_PARENT','STOP_PENDING_DRIVER')",
            (now, session_id),
        )
        return cur.rowcount > 0, None if cur.rowcount > 0 else "race"


def mark_expired_if_due(session_id: str) -> bool:
    init_schema()
    now = int(time.time())
    with _connect() as c:
        cur = c.execute(
            "UPDATE sentinel_sessions SET state = 'EXPIRED', ended_at = ? "
            "WHERE session_id = ? "
            "AND state NOT IN ('ENDED','EXPIRED') AND expires_at <= ?",
            (now, session_id, now),
        )
        return cur.rowcount > 0


def detect_signal_loss(session_id: str, threshold_seconds: int) -> bool:
    """Mark and return True iff signal-lost transitions OFF→ON this call."""
    init_schema()
    now = int(time.time())
    with _connect() as c:
        row = c.execute(
            "SELECT state, last_update_at, signal_lost_active "
            "FROM sentinel_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None or row["state"] not in (
            "ACTIVE", "STOP_PENDING_PARENT", "STOP_PENDING_DRIVER"
        ):
            return False
        last = row["last_update_at"]
        if last is None or (now - int(last)) < threshold_seconds:
            return False
        if int(row["signal_lost_active"]) == 1:
            return False
        c.execute(
            "UPDATE sentinel_sessions SET signal_lost_active = 1 "
            "WHERE session_id = ?", (session_id,),
        )
        return True


def fire_low_battery_once(session_id: str) -> bool:
    init_schema()
    with _connect() as c:
        cur = c.execute(
            "UPDATE sentinel_sessions SET low_battery_fired = 1 "
            "WHERE session_id = ? AND low_battery_fired = 0",
            (session_id,),
        )
        return cur.rowcount > 0


def add_event(session_id: str, event_type: str, payload: dict | None = None) -> int:
    init_schema()
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO sentinel_events (session_id, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                session_id,
                event_type,
                json.dumps(payload or {}, separators=(",", ":")),
                int(time.time()),
            ),
        )
        return int(cur.lastrowid)


def list_events(session_id: str, limit: int = 50) -> list[dict]:
    init_schema()
    with _connect() as c:
        rows = c.execute(
            "SELECT id, event_type, payload_json, created_at "
            "FROM sentinel_events WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, int(limit)),
        ).fetchall()
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except Exception:
            payload = {}
        out.append({
            "id": r["id"],
            "event_type": r["event_type"],
            "payload": payload,
            "created_at": r["created_at"],
        })
    return out


def set_push_token(
    session_id: str, role: str, fcm_token: str | None, platform: str | None
) -> bool:
    """Bind / clear an FCM token for the given role on a session."""
    init_schema()
    if role not in ("parent", "driver"):
        return False
    tok_col = f"{role}_fcm_token"
    plt_col = f"{role}_platform"
    with _connect() as c:
        cur = c.execute(
            f"UPDATE sentinel_sessions SET {tok_col} = ?, {plt_col} = ? "
            f"WHERE session_id = ?",
            (fcm_token, platform, session_id),
        )
        return cur.rowcount > 0


def purge_old(grace_seconds: int = 600) -> int:
    """Delete only sessions that are terminal AND past grace AND have
    no unacknowledged SOS. Live sessions are NEVER deleted — see
    anti_cut_engine.assert_no_silent_deletion.
    """
    init_schema()
    cutoff = int(time.time()) - grace_seconds
    with _connect() as c:
        rows = c.execute(
            """
            SELECT session_id FROM sentinel_sessions
            WHERE state IN ('ENDED','EXPIRED')
              AND COALESCE(ended_at, created_at) < ?
              AND (sos_active = 0 OR sos_ack_at IS NOT NULL)
            """,
            (cutoff,),
        ).fetchall()
        n = 0
        for r in rows:
            sid = r["session_id"]
            c.execute("DELETE FROM sentinel_events WHERE session_id = ?", (sid,))
            c.execute("DELETE FROM sentinel_sessions WHERE session_id = ?", (sid,))
            n += 1
    return n


def health_counters() -> dict:
    init_schema()
    now = int(time.time())
    with _connect() as c:
        row = c.execute(
            """
            SELECT
              SUM(CASE WHEN state='PENDING_DRIVER' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN state='ACTIVE' THEN 1 ELSE 0 END) AS active,
              SUM(CASE WHEN state IN ('STOP_PENDING_PARENT','STOP_PENDING_DRIVER') THEN 1 ELSE 0 END) AS stop_pending,
              SUM(CASE WHEN state='ENDED' THEN 1 ELSE 0 END) AS ended,
              SUM(CASE WHEN state='EXPIRED' THEN 1 ELSE 0 END) AS expired,
              SUM(CASE WHEN sos_active=1 AND sos_ack_at IS NULL THEN 1 ELSE 0 END) AS sos_unack,
              COUNT(*) AS total
            FROM sentinel_sessions
            """
        ).fetchone()
    return {
        "pending": int(row["pending"] or 0),
        "active": int(row["active"] or 0),
        "stop_pending": int(row["stop_pending"] or 0),
        "ended": int(row["ended"] or 0),
        "expired": int(row["expired"] or 0),
        "sos_unack": int(row["sos_unack"] or 0),
        "total": int(row["total"] or 0),
        "server_time": now,
    }
