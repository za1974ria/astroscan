"""Session manager — orchestrates the lifecycle endpoints.

All state-changing flows live here so ``routes.py`` stays thin and
purely HTTP. The manager calls into ``store``, ``consent_engine``,
``anti_cut_engine``, ``alert_engine``, and ``audit_logger`` — never
the other way around.
"""
from __future__ import annotations

import secrets
import time

from app.blueprints.sentinel import (
    alert_engine,
    anti_cut_engine,
    audit_logger,
    consent_engine,
    push_engine,
    state_machine as fsm,
    store,
    telemetry_engine,
    tokens,
)


class SessionError(Exception):
    def __init__(self, code: int, error: str):
        super().__init__(error)
        self.code = code
        self.error = error


# ── Create / Accept ──────────────────────────────────────────────────

def create_session(params: dict) -> dict:
    """``params`` is the schemas.validate_create output."""
    session_id = secrets.token_urlsafe(16)
    parent_token, driver_token = tokens.make_tokens(session_id)
    now = int(time.time())
    row = {
        "session_id": session_id,
        "parent_token": parent_token,
        "driver_token": driver_token,
        "driver_label": params["driver_label"],
        "speed_limit_kmh": params["speed_limit_kmh"],
        "ttl_seconds": params["ttl_seconds"],
        "created_at": now,
        "expires_at": now + params["ttl_seconds"],
        "safe_zone_lat": params["safe_zone_lat"],
        "safe_zone_lon": params["safe_zone_lon"],
        "safe_zone_radius_m": params["safe_zone_radius_m"],
    }
    store.insert_session(row)
    store.purge_old()
    audit_logger.session_created(
        session_id,
        params["ttl_seconds"],
        params["speed_limit_kmh"],
        params["safe_zone_radius_m"] is not None,
    )
    return {
        "session_id": session_id,
        "parent_token": parent_token,
        "driver_token": driver_token,
        "expires_at": row["expires_at"],
        "ttl_seconds": params["ttl_seconds"],
        "speed_limit_kmh": params["speed_limit_kmh"],
        "driver_label": params["driver_label"],
        "safe_zone": (
            None if params["safe_zone_radius_m"] is None
            else {
                "lat": params["safe_zone_lat"],
                "lon": params["safe_zone_lon"],
                "radius_m": params["safe_zone_radius_m"],
            }
        ),
    }


def accept_session(driver_sid: str) -> None:
    result = consent_engine.attempt_accept(driver_sid)
    if not result.ok:
        # Map to HTTP codes
        if result.reason == "session_not_found":
            raise SessionError(404, "session_not_found")
        raise SessionError(409, result.reason or "cannot_accept")


# ── Update ───────────────────────────────────────────────────────────

def push_position(driver_sid: str, pos: dict) -> dict:
    row = store.get_session(driver_sid)
    if row is None:
        raise SessionError(404, "session_not_found")
    if int(row["expires_at"]) <= int(time.time()):
        if store.mark_expired_if_due(driver_sid):
            audit_logger.session_expired(driver_sid)
        raise SessionError(410, "session_expired")
    if not consent_engine.assert_consent_for_update(row["state"]):
        raise SessionError(410, f"state_{row['state'].lower()}")
    return alert_engine.evaluate_update(driver_sid, row, pos)


# ── State ────────────────────────────────────────────────────────────

def public_state(sid: str, role: str) -> dict:
    # Lazy auto-expire on every read so stale tabs reflect reality.
    row = store.get_session(sid)
    if row is None:
        raise SessionError(404, "session_not_found")
    if int(row["expires_at"]) <= int(time.time()) and row["state"] not in fsm.TERMINAL:
        if store.mark_expired_if_due(sid):
            audit_logger.session_expired(sid)
            push_engine.notify(sid, "both", "session_expired")
    # Signal-loss detection (state read is the cheap heartbeat for this).
    from app.blueprints.sentinel.routes import SIGNAL_LOSS_THRESHOLD
    if store.detect_signal_loss(sid, SIGNAL_LOSS_THRESHOLD):
        audit_logger.signal_lost(sid, SIGNAL_LOSS_THRESHOLD)
        push_engine.notify(sid, "parent", "signal_lost")
    payload = telemetry_engine.public_state(sid, role)
    if payload is None:
        raise SessionError(404, "session_not_found")
    return payload


# ── SOS ──────────────────────────────────────────────────────────────

def trigger_sos(driver_sid: str) -> bool:
    row = store.get_session(driver_sid)
    if row is None:
        raise SessionError(404, "session_not_found")
    if row["state"] in fsm.TERMINAL:
        raise SessionError(410, "session_not_live")
    fired = store.trigger_sos(driver_sid)
    if fired:
        audit_logger.sos_triggered(driver_sid)
        push_engine.notify(driver_sid, "parent", "sos_triggered")
    return fired


def ack_sos(parent_sid: str) -> None:
    if not store.ack_sos(parent_sid):
        raise SessionError(409, "no_pending_sos")
    audit_logger.sos_acknowledged(parent_sid)
    push_engine.notify(parent_sid, "driver", "sos_acknowledged")


# ── Dual-stop ────────────────────────────────────────────────────────

def request_stop(sid: str, requester: str) -> dict:
    row = store.get_session(sid)
    if row is None:
        raise SessionError(404, "session_not_found")
    anti_cut_engine.assert_no_unilateral_termination(sid, row["state"], requester)
    if not fsm.can_request_stop(row["state"], requester):
        raise SessionError(409, f"cannot_request_stop_in_state_{row['state'].lower()}")
    new_state = fsm.state_after_request(requester)
    if not store.request_stop(sid, requester, new_state):
        raise SessionError(409, "stop_request_failed")
    audit_logger.stop_requested(sid, requester)
    # Notify the counter-party (the one who has to approve).
    target = fsm.approver_for(new_state)
    if target:
        push_engine.notify(sid, target, "stop_requested", {"by": requester})
    return {
        "state": new_state,
        "awaiting_approval_from": target,
    }


def approve_stop(sid: str, approver: str) -> None:
    changed, reason = store.approve_stop(sid, approver)
    if not changed:
        raise SessionError(409, reason or "cannot_approve")
    audit_logger.stop_approved(sid, approver)
    # The approver is the counter-party; notify the original requester (the other role).
    other = "driver" if approver == "parent" else "parent"
    push_engine.notify(sid, other, "stop_approved", {"by": approver})
