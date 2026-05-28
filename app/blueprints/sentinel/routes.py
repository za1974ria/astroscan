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

from flask import Blueprint, Response, abort, redirect, render_template, request, send_from_directory, url_for

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
# Acte 1 UX v2 (2026-05-15) — TTL plage 1 min ≤ ttl ≤ 12 h (was fixe 90 min).
MAX_TTL_SECONDS = 720 * 60   # 12 hours
MIN_TTL_SECONDS = 60         # 1 minute minimum
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


# ─────────────────────────────────────────────────────── APK distribution
# Serve the Android APKs at /modules/sentinel/<filename>.apk with the proper
# package-archive mimetype so Chrome/Edge trigger the install flow on Android.
# Files live in /opt/astroscan/static/downloads/ (no duplication).

_APK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "static", "downloads",
)
_APK_ALLOWED = frozenset({"sentinel-parent.apk", "sentinel-driver.apk"})


@sentinel_bp.route("/modules/sentinel/<path:filename>", methods=["GET"])
def sentinel_assets(filename: str):
    if filename not in _APK_ALLOWED:
        abort(404)
    return send_from_directory(
        _APK_DIR,
        filename,
        as_attachment=False,
        mimetype="application/vnd.android.package-archive",
    )


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
    # Zero-knowledge analytics: country counter, IP never persisted.
    try:
        from app.services.geoip_counter import get_geoip_counter
        client_ip = (request.headers.get("X-Forwarded-For")
                     or request.remote_addr
                     or "").split(",")[0].strip()
        if client_ip:
            country = get_geoip_counter().resolve_country(client_ip)
            with store._connect() as _conn:
                get_geoip_counter().increment_counter(country, _conn)
            del client_ip
    except Exception:
        log.warning("geoip_counter failed (non-blocking)")
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


@sentinel_bp.route("/api/sentinel/stats", methods=["GET"])
def api_sentinel_stats():
    """Public zero-knowledge analytics dashboard.

    Exposes ONLY aggregated country counters. No IP, no session id,
    no token, no PII. Conforms to GDPR Article 89.
    """
    try:
        from app.services.geoip_counter import get_geoip_counter
        return api_ok(**get_geoip_counter().get_stats())
    except Exception:
        log.exception("[SENTINEL] stats unavailable")
        return api_error("stats_unavailable", code=503)


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


# ─────────────────────────── PHASE 4-5-9 (2026-05-23) — Trust layer ────
# Public read-only metrics for the landing trust block + secure POST
# feedback. SQL-FIRST: source of truth = sentinel_sessions. Defense in
# depth: JSON content-type, size cap, origin/referer check, honeypot,
# rate-limit, sanitize, ip_hash only.

import hashlib as _b5_hashlib
import time as _b5_time
from urllib.parse import urlsplit as _b5_urlsplit

_FEEDBACK_MAX_BYTES = 4096
_FEEDBACK_TRUSTED_ORIGINS = (
    "https://astroscan.space",
    "https://www.astroscan.space",
    "http://127.0.0.1:5003",
    "http://127.0.0.1:5004",
    "http://localhost:5003",
)
_FEEDBACK_DAILY_HASH_CAP = 10
_FEEDBACK_DAILY_HITS_LOCK_KEY = "sentinel_feedback_daily_hash"


def _client_ip_hash(req) -> str:
    """SHA256 + truncate (16 hex) — never store raw IP."""
    from app.services.security import _client_ip_from_request
    ip = _client_ip_from_request(req) or ""
    return _b5_hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def _origin_referer_ok(req) -> bool:
    """Check Origin and Referer against trusted list. Returns True if at least
    one is present AND matches. POST CSRF defense-in-depth."""
    candidates = []
    origin = (req.headers.get("Origin") or "").strip()
    if origin:
        candidates.append(origin)
    referer = (req.headers.get("Referer") or "").strip()
    if referer:
        parts = _b5_urlsplit(referer)
        if parts.scheme and parts.netloc:
            candidates.append(f"{parts.scheme}://{parts.netloc}")
    if not candidates:
        # No Origin and no Referer = likely curl/script → reject for POST feedback.
        return False
    for c in candidates:
        if c in _FEEDBACK_TRUSTED_ORIGINS:
            return True
    return False


# In-memory daily counter per ip_hash (process-local; 4 workers => effective ~4x
# but combined with /minute rate-limit at the @rate_limit_ip decorator level it
# remains within the brief envelope; durable cross-worker enforcement is a
# Redis-level concern outside Phase 4 scope).
_FB_DAILY: dict[str, list[int]] = {}


def _check_daily_hash_cap(ip_hash: str) -> bool:
    """Returns True if under daily cap (10/day/ip_hash)."""
    now_ts = int(_b5_time.time())
    cutoff = now_ts - 86400
    hits = [t for t in _FB_DAILY.get(ip_hash, []) if t >= cutoff]
    if len(hits) >= _FEEDBACK_DAILY_HASH_CAP:
        _FB_DAILY[ip_hash] = hits
        return False
    hits.append(now_ts)
    _FB_DAILY[ip_hash] = hits
    # Garde-fou mémoire (best-effort cleanup of stale buckets)
    if len(_FB_DAILY) > 2000:
        for k in list(_FB_DAILY.keys())[:500]:
            arr = _FB_DAILY.get(k) or []
            if not arr or arr[-1] < cutoff:
                _FB_DAILY.pop(k, None)
    return True


@sentinel_bp.route("/api/sentinel/metrics", methods=["GET"])
def api_sentinel_metrics():
    """Public read-only trust metrics for the landing block.

    SQL-FIRST: SELECT COUNT(*) FROM sentinel_sessions / sentinel_feedback.
    Always returns 200 with a snapshot ; fail-safe defaults if DB unavailable.
    No auth, no PII, no IP, no tokens exposed. Cacheable 30 s client-side.
    """
    try:
        from app.services.sentinel_metrics import get_metrics_snapshot
        snap = get_metrics_snapshot()
    except Exception as exc:  # noqa: BLE001
        log.warning("[SENTINEL] metrics snapshot failure: %s", exc)
        snap = {
            "total_sessions": 0, "completed_sessions": 0, "active_users": 0,
            "feedback_count": 0, "feedback_avg": 0.0, "ok": True, "cache_ttl_s": 30,
        }
    resp = api_ok(**snap)
    resp.headers["Cache-Control"] = "public, max-age=30"
    return resp


@sentinel_bp.route("/api/sentinel/feedback", methods=["POST"])
@rate_limit_ip(max_per_minute=2, key_prefix="sentinel_feedback")
def api_sentinel_feedback():
    """Submit user feedback (suggestion / bug / ux / idea / security_incident).

    Defense in depth (CHANTIER 9):
      1. Strict Content-Type application/json
      2. Payload size cap 4 KB
      3. Origin + Referer validation against allowlist
      4. Honeypot 'website' field — must be empty
      5. Rate limit 2/min/IP via @rate_limit_ip
      6. Soft daily cap 10/day/ip_hash (process-local)
      7. Schema validation (rating 1-5, category whitelist, message sanitize)
      8. ip_hash only (SHA256 truncated 16 hex), never raw IP

    Returns 200 {"ok": true} on success, 4xx with reason code otherwise.
    """
    # 1. Strict Content-Type
    ct = (request.headers.get("Content-Type") or "").lower()
    if not ct.startswith("application/json"):
        return api_error("content_type_must_be_json", code=415)

    # 2. Size cap (Content-Length check + body re-read defensively)
    cl = request.headers.get("Content-Length")
    if cl is not None:
        try:
            if int(cl) > _FEEDBACK_MAX_BYTES:
                return api_error("payload_too_large", code=413)
        except ValueError:
            return api_error("invalid_content_length", code=400)
    raw = request.get_data(cache=False, as_text=False) or b""
    if len(raw) > _FEEDBACK_MAX_BYTES:
        return api_error("payload_too_large", code=413)

    # 3. Origin + Referer check
    if not _origin_referer_ok(request):
        return api_error("origin_not_allowed", code=403)

    # 4. Parse JSON safely (force=False — Content-Type checked above)
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return api_error("invalid_json", code=400)

    # 5. Schema validation (includes honeypot check + sanitization)
    try:
        cleaned = schemas.validate_feedback(payload)
    except schemas.ValidationError as ve:
        return api_error(str(ve), code=400)

    # 6. ip_hash + daily cap
    ip_hash = _client_ip_hash(request)
    if not _check_daily_hash_cap(ip_hash):
        return api_error("daily_cap_exceeded", code=429)

    # 7. DB insert (fail-safe — UI gets 503 if DB write blocked)
    ua = (request.headers.get("User-Agent") or "")[:300]
    status = "priority" if cleaned["is_priority"] else "new"
    try:
        with store._connect() as c:
            c.execute(
                "INSERT INTO sentinel_feedback "
                "(created_at, rating, category, message, email, user_agent, ip_hash, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(_b5_time.time()),
                    cleaned["rating"],
                    cleaned["category"],
                    cleaned["message"] or None,
                    cleaned["email"],
                    ua,
                    ip_hash,
                    status,
                ),
            )
    except Exception:
        log.exception("[SENTINEL] feedback insert failure")
        return api_error("feedback_storage_unavailable", code=503)

    # 8. Log priority feedback at WARNING level for ops visibility (no PII)
    if status == "priority":
        log.warning(
            "[SENTINEL] priority feedback received category=%s rating=%d ip_hash=%s",
            cleaned["category"], cleaned["rating"], ip_hash,
        )
    return api_ok(ok=True)
