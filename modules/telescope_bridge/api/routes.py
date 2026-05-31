"""AstroScan Telescope Bridge — Flask blueprint.

Hardware posture (verifiable by grep on this file):
  - Telescope hardware remains READ-ONLY. This module exposes ZERO
    motion-related identifiers (slew/park/goto/move/pulse/sync/motor
    never appear in executable code).
  - No subprocess, no os.system, no shell, no external HTTP from this
    file. The only side effects are sqlite writes in
    `modules.telescope_bridge.services.storage` (pairing records +
    append-only telemetry — separate DB from the main app).
  - Every response embeds `read_only:true` and
    `dangerous_actions_enabled:false` via `_safety_envelope()`.

Pairing model:
  - POST /pair/request {label} -> {pairing_token} (single-use, TTL 300s)
  - POST /pair/confirm {pairing_token, agent_id, devices}
        -> {status:"paired", agent_id}
  - POST /telemetry/push  {agent_id, telemetry} -> {status:"ok"}
        (rejected if agent_id is not paired)
  - GET  /devices  reflects the real agent registry, so an agent that
        already paired in a previous run can detect itself and skip a
        new pairing instead of looping.

The blueprint is mounted by `app/__init__.py` ONLY when:
    os.environ.get("FEATURE_TELESCOPE_BRIDGE") in {"1","true","yes","on"}
When disabled, this module is NOT imported and every TB endpoint
returns Flask's default 404 — no information leakage about its
existence.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from modules.telescope_bridge.services import storage as tb_storage

log = logging.getLogger(__name__)

# ── Module-level constants ───────────────────────────────────────────
TB_API_VERSION = "1"
TB_MODULE_VERSION = "0.3.0-tb35-pairing"

# Hardware safety posture — hard-coded. Flipping these to mutable
# values would require a separate engineering decision and a security
# review.
READ_ONLY = True
DANGEROUS_ACTIONS_ENABLED = False


def _mock_enabled() -> bool:
    return os.environ.get("TB_MOCK", "0").strip() in ("1", "true", "yes", "on")


# Main API blueprint — mounted with url_prefix="/api/telescope-bridge".
bp = Blueprint("telescope_bridge", __name__)

# Companion blueprint reserved for future TB-38 dashboard pages.
# Kept empty for now so the import in `app/__init__.py` succeeds; adding
# UI routes does not require touching the app registration code.
pages_bp = Blueprint("telescope_bridge_pages", __name__)


# ── Helpers ──────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safety_envelope() -> dict:
    """Fields embedded in EVERY TB endpoint response."""
    return {
        "read_only": READ_ONLY,
        "dangerous_actions_enabled": DANGEROUS_ACTIONS_ENABLED,
        "api_version": TB_API_VERSION,
        "module_version": TB_MODULE_VERSION,
        "served_at": _now_iso(),
    }


def _envelope_response(payload: dict, http_status: int = 200):
    body = _safety_envelope()
    body.update(payload)
    return jsonify(body), http_status


def _safe_str(value, max_len: int = 128) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_len]


# ── Read-only endpoints (existing surface) ───────────────────────────
@bp.get("/health")
def health():
    return _envelope_response({
        "enabled": True,
        "status": "ok",
        "phase": "TB-35 pairing live",
        "mock_mode": _mock_enabled(),
    })


@bp.get("/capabilities")
def capabilities():
    """Static declaration of the V1 capability surface.

    `movement_commands` MUST remain empty in V1. `post_endpoints_exposed`
    is now true because pairing/telemetry POSTs are wired, but those
    endpoints intentionally do NOT command the telescope — they only
    persist records.
    """
    return _envelope_response({
        "ecosystems": ["ASCOM-Alpaca", "INDI"],
        "modes": ["read-only"],
        "device_kinds_supported": [
            "mount", "camera", "focuser", "filterwheel",
            "rotator", "dome", "weather", "guider",
        ],
        "movement_commands": [],
        "post_endpoints_exposed": True,
        "post_endpoints": ["/pair/request", "/pair/confirm", "/telemetry/push"],
    })


@bp.get("/devices")
def devices():
    """Real agent registry from storage.

    Shape matches what the cloud client expects (`agent_id`, `label`,
    `devices`, `paired_at`) so `CloudBridgeClient.is_paired()` can detect
    an existing pairing and skip a redundant /pair/request round-trip.
    """
    try:
        agents = tb_storage.list_agents()
    except Exception as e:
        log.warning("telescope_bridge devices: %s", e)
        agents = []
    return _envelope_response({
        "devices": agents,
        "count": len(agents),
        "source": "registry",
    })


@bp.get("/telemetry/latest")
def telemetry_latest():
    """Mock telemetry (kept for the dashboard contract). Real ingestion
    goes through `/telemetry/push` and is persisted in `tb_telemetry`;
    that table is read by future TB-38 endpoints, not here."""
    payload = {
        "status": "not_connected",
        "device_id": None,
        "kind": None,
        "sample": None,
    }
    if _mock_enabled():
        payload = {
            "status": "mock",
            "device_id": "mock-mount-0",
            "kind": "mount",
            "sample": {
                "ts": _now_iso(),
                "ra_hours": 5.123,
                "dec_degrees": 12.345,
                "is_tracking": False,
            },
        }
    return _envelope_response(payload)


# ── Pairing & telemetry POSTs (TB-35) ────────────────────────────────
@bp.post("/pair/request")
def pair_request():
    """Issue a single-use pairing token (TTL 300s)."""
    data = request.get_json(silent=True) or {}
    label = _safe_str(data.get("label", ""), 128)
    try:
        info = tb_storage.create_pair_token(label=label)
    except Exception as e:
        log.exception("pair_request failed")
        return _envelope_response({"error": "storage_failure"}, 500)
    return _envelope_response({
        "pairing_token": info["pairing_token"],
        "expires_in_seconds": info["expires_in_seconds"],
        "label": info["label"],
    })


@bp.post("/pair/confirm")
def pair_confirm():
    """Atomically consume a pairing token and register the agent."""
    data = request.get_json(silent=True) or {}
    token = _safe_str(data.get("pairing_token", ""), 256)
    agent_id = _safe_str(data.get("agent_id", ""), 128)
    raw_devices = data.get("devices", [])
    if not token:
        return _envelope_response(
            {"error": "missing_field", "field": "pairing_token"}, 400,
        )
    if not agent_id:
        return _envelope_response(
            {"error": "missing_field", "field": "agent_id"}, 400,
        )
    if not isinstance(raw_devices, list):
        return _envelope_response(
            {"error": "invalid_field", "field": "devices",
             "expected": "list"}, 400,
        )
    if len(raw_devices) > 64:
        return _envelope_response(
            {"error": "too_many_devices", "limit": 64}, 400,
        )

    ok, reason = tb_storage.consume_pair_token(token, agent_id)
    if not ok:
        http = 403 if reason in ("expired", "already_consumed") else 400
        return _envelope_response(
            {"error": "pairing_token_" + reason}, http,
        )

    label = _safe_str(data.get("label", ""), 128) or agent_id
    try:
        tb_storage.register_agent(agent_id, label, raw_devices)
    except Exception:
        log.exception("register_agent failed")
        return _envelope_response({"error": "storage_failure"}, 500)
    return _envelope_response({
        "status": "paired",
        "agent_id": agent_id,
        "devices_count": len(raw_devices),
    })


@bp.post("/telemetry/push")
def telemetry_push():
    """Persist a telemetry sample. Rejects unpaired agent_id.

    This endpoint NEVER commands the telescope — it only writes to the
    `tb_telemetry` table. The hardware read-only posture documented at
    the top of this file is unaffected.
    """
    data = request.get_json(silent=True) or {}
    agent_id = _safe_str(data.get("agent_id", ""), 128)
    telemetry = data.get("telemetry")
    if not agent_id:
        return _envelope_response(
            {"error": "missing_field", "field": "agent_id"}, 400,
        )
    if telemetry is None:
        return _envelope_response(
            {"error": "missing_field", "field": "telemetry"}, 400,
        )
    if not tb_storage.agent_exists(agent_id):
        return _envelope_response(
            {"error": "agent_not_paired", "agent_id": agent_id}, 403,
        )
    try:
        info = tb_storage.store_telemetry(agent_id, telemetry)
    except Exception:
        log.exception("store_telemetry failed")
        return _envelope_response({"error": "storage_failure"}, 500)
    return _envelope_response({
        "status": "ok",
        "ingested_at": info["ingested_at"],
        "bytes": info["bytes"],
    })
