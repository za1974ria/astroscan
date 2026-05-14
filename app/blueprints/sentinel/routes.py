"""ASTROSCAN SENTINEL — flagship route layer.

Legal / ethical posture (non-negotiable, baked into every module):

  - "Protected trip", "family safety", "temporary safety session".
    NEVER framed as surveillance, monitoring, or tracking.
  - Driver explicit consent BEFORE any geolocation API call.
  - No IMEI, no telecom, no stealth, no spyware, no background
    tracking. The user opens a tab on their own device and shares
    location voluntarily and visibly.
  - Time-bounded (30 / 60 / 90 min hard cap, server-enforced).
  - Dual-stop: neither party can casually end a live session alone.
    TTL expiry is the only unilateral terminator (server-driven).
  - SOS is an alert, not an end — the session keeps going so the
    parent can keep helping.
  - Positions live exclusively on the active session row, never
    written to events, never to logs. Audit logs contain
    ``session_id`` + event type only.

URL surface — UNIFIED:
  GET  /sentinel
  GET  /sentinel/driver/<token>          (invite + cockpit on one URL)
  GET  /sentinel/parent/<token>          (parent live)
  POST /api/sentinel/session/create
  POST /api/sentinel/session/accept
  POST /api/sentinel/session/update
  GET  /api/sentinel/session/<token>/state
  POST /api/sentinel/session/sos
  POST /api/sentinel/session/sos_ack
  POST /api/sentinel/session/stop_request
  POST /api/sentinel/session/stop_approve
  GET  /api/sentinel/health

Deprecation redirects:
  GET /vehicle-secure-locator  -> 301 /sentinel
  GET /vehicle                 -> 301 /sentinel
  GET /guardian-family         -> 301 /sentinel
"""
from __future__ import annotations

import logging

import json
import os

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for

from app.blueprints.sentinel import (
    push_engine,
    schemas,
    session_manager as sm,
    speed_engine,
    store,
    tokens,
)
from app.blueprints.sentinel.anti_cut_engine import AntiCutViolation
from app.services.security import rate_limit_ip
from app.utils.responses import api_error, api_ok

log = logging.getLogger("astroscan.sentinel")

sentinel_bp = Blueprint("sentinel", __name__, url_prefix="")

# Public constants (also exposed via /health for the frontend)
MAX_TTL_SECONDS = 90 * 60
SOS_HOLD_SECONDS = 3
SIGNAL_LOSS_THRESHOLD = 30
UPDATE_INTERVAL_SECONDS = 5


def _auth(token: str, role: str | None = None) -> dict:
    return tokens.load_token(
        token, max_age_seconds=MAX_TTL_SECONDS, expected_role=role
    )


def _abs(endpoint: str, **values) -> str:
    return url_for(endpoint, _external=True, **values)


def _handle_session_error(e: sm.SessionError):
    return api_error(e.error, code=e.code)


# ─────────────────────────────────────────────────────── Pages

@sentinel_bp.route("/sentinel", methods=["GET"])
def landing():
    return render_template(
        "sentinel/landing.html",
        max_ttl_seconds=MAX_TTL_SECONDS,
    )


@sentinel_bp.route("/sentinel/driver/<token>", methods=["GET"])
def driver_page(token: str):
    try:
        decoded = _auth(token, "driver")
    except tokens.TokenError:
        abort(404)
    row = store.get_session(decoded["sid"])
    if not row:
        abort(404)
    return render_template(
        "sentinel/driver.html",
        driver_token=token,
        driver_label=row.get("driver_label") or "",
        speed_limit_kmh=row["speed_limit_kmh"],
        ttl_minutes=row["ttl_seconds"] // 60,
        sos_hold_seconds=SOS_HOLD_SECONDS,
        update_interval=UPDATE_INTERVAL_SECONDS,
        initial_state=row["state"],
    )


@sentinel_bp.route("/sentinel/parent/<token>", methods=["GET"])
def parent_page(token: str):
    try:
        _auth(token, "parent")
    except tokens.TokenError:
        abort(404)
    return render_template(
        "sentinel/parent.html",
        parent_token=token,
        update_interval=UPDATE_INTERVAL_SECONDS,
    )


# ─────────────────────────────────────────────────────── Deprecation redirects

@sentinel_bp.route("/vehicle-secure-locator", methods=["GET"])
@sentinel_bp.route("/vehicle", methods=["GET"])
@sentinel_bp.route("/guardian-family", methods=["GET"])
def deprecated_redirect():
    return redirect(url_for("sentinel.landing"), code=301)


# ─────────────────────────────────────────────────────── Android App Links
# Hosted at https://astroscan.space/.well-known/assetlinks.json so the Android
# system can verify the autoVerify intent-filter in both apps' manifest.
# Fingerprints are filled in once the production signing keystore is provisioned;
# the placeholder file ships with empty `sha256_cert_fingerprints` arrays.

_ASSETLINKS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "static", ".well-known", "assetlinks.json",
)


@sentinel_bp.route("/.well-known/assetlinks.json", methods=["GET"])
def assetlinks():
    try:
        with open(_ASSETLINKS_PATH, "rb") as f:
            return Response(f.read(), mimetype="application/json")
    except FileNotFoundError:
        return Response(json.dumps([]), mimetype="application/json"), 404


# ─────────────────────────────────────────────────────── API

@sentinel_bp.route("/api/sentinel/session/create", methods=["POST"])
@rate_limit_ip(max_per_minute=6, key_prefix="snt_create")
def api_create():
    payload = request.get_json(silent=True) or {}
    try:
        params = schemas.validate_create(payload)
    except schemas.ValidationError as e:
        return api_error(str(e), code=400)
    result = sm.create_session(params)
    result["parent_url"] = _abs("sentinel.parent_page", token=result["parent_token"])
    result["invite_url"] = _abs("sentinel.driver_page", token=result["driver_token"])
    result["update_interval"] = UPDATE_INTERVAL_SECONDS
    return api_ok(**result)


@sentinel_bp.route("/api/sentinel/session/accept", methods=["POST"])
@rate_limit_ip(max_per_minute=12, key_prefix="snt_accept")
def api_accept():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token, "driver")
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    try:
        sm.accept_session(decoded["sid"])
    except sm.SessionError as e:
        return _handle_session_error(e)
    return api_ok(status="active")


@sentinel_bp.route("/api/sentinel/session/update", methods=["POST"])
@rate_limit_ip(max_per_minute=30, key_prefix="snt_update")
def api_update():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token, "driver")
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    try:
        pos = schemas.validate_position(payload)
    except schemas.ValidationError as e:
        return api_error(str(e), code=400)
    try:
        summary = sm.push_position(decoded["sid"], pos)
    except sm.SessionError as e:
        return _handle_session_error(e)
    return api_ok(status="ok", **summary)


@sentinel_bp.route("/api/sentinel/session/<token>/state", methods=["GET"])
@rate_limit_ip(max_per_minute=120, key_prefix="snt_state")
def api_state(token: str):
    try:
        decoded = _auth(token)
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    role = decoded["role"]
    if role not in ("parent", "driver"):
        return api_error("token_wrong_role", code=401)
    try:
        payload = sm.public_state(decoded["sid"], role)
    except sm.SessionError as e:
        return _handle_session_error(e)
    return api_ok(**payload)


@sentinel_bp.route("/api/sentinel/session/sos", methods=["POST"])
@rate_limit_ip(max_per_minute=6, key_prefix="snt_sos")
def api_sos():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token, "driver")
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    try:
        fired = sm.trigger_sos(decoded["sid"])
    except sm.SessionError as e:
        return _handle_session_error(e)
    return api_ok(status="sos_active", was_new=fired)


@sentinel_bp.route("/api/sentinel/session/sos_ack", methods=["POST"])
@rate_limit_ip(max_per_minute=12, key_prefix="snt_sos_ack")
def api_sos_ack():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token, "parent")
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    try:
        sm.ack_sos(decoded["sid"])
    except sm.SessionError as e:
        return _handle_session_error(e)
    return api_ok(status="sos_acknowledged")


@sentinel_bp.route("/api/sentinel/session/stop_request", methods=["POST"])
@rate_limit_ip(max_per_minute=6, key_prefix="snt_stop_req")
def api_stop_request():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token)
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    requester = decoded["role"]
    if requester not in ("parent", "driver"):
        return api_error("token_wrong_role", code=401)
    try:
        result = sm.request_stop(decoded["sid"], requester)
    except AntiCutViolation as e:
        return api_error(f"anti_cut_{e}", code=403)
    except sm.SessionError as e:
        return _handle_session_error(e)
    return api_ok(status=result["state"].lower(),
                  awaiting_approval_from=result["awaiting_approval_from"])


@sentinel_bp.route("/api/sentinel/session/stop_approve", methods=["POST"])
@rate_limit_ip(max_per_minute=6, key_prefix="snt_stop_app")
def api_stop_approve():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token)
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    approver = decoded["role"]
    if approver not in ("parent", "driver"):
        return api_error("token_wrong_role", code=401)
    try:
        sm.approve_stop(decoded["sid"], approver)
    except sm.SessionError as e:
        return _handle_session_error(e)
    return api_ok(status="ended")


@sentinel_bp.route("/api/sentinel/session/push/register", methods=["POST"])
@rate_limit_ip(max_per_minute=12, key_prefix="snt_push_reg")
def api_push_register():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token)
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    role = decoded["role"]
    if role not in ("parent", "driver"):
        return api_error("token_wrong_role", code=401)
    try:
        fcm_token, platform = schemas.validate_push_register(payload)
    except schemas.ValidationError as e:
        return api_error(str(e), code=400)
    if not store.set_push_token(decoded["sid"], role, fcm_token, platform):
        return api_error("session_not_found", code=404)
    log.info("[SENTINEL] push_registered sid=%s role=%s platform=%s",
             decoded["sid"], role, platform)
    return api_ok(
        status="registered",
        push_enabled=push_engine.is_configured(),
    )


@sentinel_bp.route("/api/sentinel/session/push/unregister", methods=["POST"])
@rate_limit_ip(max_per_minute=12, key_prefix="snt_push_unreg")
def api_push_unregister():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token)
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    role = decoded["role"]
    if role not in ("parent", "driver"):
        return api_error("token_wrong_role", code=401)
    store.set_push_token(decoded["sid"], role, None, None)
    log.info("[SENTINEL] push_unregistered sid=%s role=%s", decoded["sid"], role)
    return api_ok(status="unregistered")


@sentinel_bp.route("/api/sentinel/session/update/batch", methods=["POST"])
@rate_limit_ip(max_per_minute=12, key_prefix="snt_batch")
def api_update_batch():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return api_error("token_required", code=400)
    try:
        decoded = _auth(token, "driver")
    except tokens.TokenError as e:
        return api_error(f"token_{e}", code=401)
    try:
        positions = schemas.validate_batch(payload)
    except schemas.ValidationError as e:
        return api_error(str(e), code=400)
    accepted = 0
    last_summary = None
    for pos in positions:
        try:
            last_summary = sm.push_position(decoded["sid"], pos)
            accepted += 1
        except sm.SessionError as e:
            # Stop on first irrecoverable state — return what we got.
            return api_error(e.error, code=e.code, accepted=accepted)
    return api_ok(status="ok", accepted=accepted, summary=last_summary)


@sentinel_bp.route("/api/sentinel/health", methods=["GET"])
def api_health():
    try:
        counters = store.health_counters()
        return api_ok(
            module="astroscan_sentinel",
            version="1.0.0",
            max_ttl_seconds=MAX_TTL_SECONDS,
            sos_hold_seconds=SOS_HOLD_SECONDS,
            over_speed_streak_seconds=speed_engine.STREAK_REQUIRED_SECONDS,
            signal_loss_threshold_seconds=SIGNAL_LOSS_THRESHOLD,
            update_interval_seconds=UPDATE_INTERVAL_SECONDS,
            push_enabled=push_engine.is_configured(),
            sessions=counters,
        )
    except Exception as e:
        log.exception("[SENTINEL] health failure: %s", e)
        return api_error("health_failure", code=503)
