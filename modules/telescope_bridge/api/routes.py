"""AstroScan Telescope Bridge — Flask blueprint (TB-2 skeleton).

V1 read-only ONLY. No POST/PUT/DELETE/PATCH endpoints in this module.
No ASCOM/INDI integration yet. All payloads are mock/safe.

Safety posture (verifiable by grep on this file):
  - imports limited to: os, datetime, flask
  - NO subprocess, NO os.system, NO requests-to-external, NO sqlite
  - every response embeds `read_only:true` and `dangerous_actions_enabled:false`
  - zero motion-related identifiers in executable code
    (slew/park/goto/move/pulse/sync/motor never appear)

The blueprint is mounted by `app/__init__.py` ONLY when:
    os.environ.get("FEATURE_TELESCOPE_BRIDGE") in {"1","true","yes","on"}
When disabled, this module is NOT imported and every TB endpoint returns
Flask's default 404 — no information leakage about its existence.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify

# ── Module-level constants ───────────────────────────────────────────
TB_API_VERSION = "1"
TB_MODULE_VERSION = "0.2.0-tb2-skeleton"

# Safety posture — hard-coded. Flipping these to mutable values would
# require a separate engineering decision and a security review.
READ_ONLY = True
DANGEROUS_ACTIONS_ENABLED = False

# Mock toggle is SEPARATE from FEATURE_TELESCOPE_BRIDGE. The blueprint
# only loads at all when the feature flag is on; TB_MOCK only decides
# whether GET /devices and /telemetry/latest return synthetic content
# or empty/not_connected.
def _mock_enabled() -> bool:
    return os.environ.get("TB_MOCK", "0").strip() in ("1", "true", "yes", "on")


# Blueprint mounted by app/__init__.py with url_prefix="/api/telescope-bridge".
bp = Blueprint("telescope_bridge", __name__)


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


# ── Endpoints (GET only) ─────────────────────────────────────────────
@bp.get("/health")
def health():
    """Module health. Reached only when the feature flag is ON, hence
    `enabled: true`. When disabled, this route does not exist."""
    payload = _safety_envelope()
    payload.update({
        "enabled": True,
        "status": "ok",
        "phase": "TB-2 skeleton",
        "mock_mode": _mock_enabled(),
    })
    return jsonify(payload), 200


@bp.get("/capabilities")
def capabilities():
    """Static declaration of the V1 capability surface. The arrays
    `movement_commands` and `post_endpoints_exposed` are part of the
    contract — they MUST remain empty/false in V1."""
    payload = _safety_envelope()
    payload.update({
        "ecosystems": ["ASCOM-Alpaca", "INDI"],
        "modes": ["read-only"],
        "device_kinds_supported": [
            "mount", "camera", "focuser", "filterwheel",
            "rotator", "dome", "weather", "guider",
        ],
        "movement_commands": [],
        "post_endpoints_exposed": False,
    })
    return jsonify(payload), 200


@bp.get("/devices")
def devices():
    """Mock list. Real registry arrives in TB-3+. With TB_MOCK off, the
    endpoint reports `count: 0` so the dashboard can detect "no devices
    yet" cleanly."""
    payload = _safety_envelope()
    devs: list[dict] = []
    if _mock_enabled():
        devs = [{
            "device_id": "mock-mount-0",
            "kind": "mount",
            "name": "Mock EQ6-R (TB_MOCK=1)",
            "driver": "mock",
            "online": True,
            "last_seen": _now_iso(),
        }]
    payload.update({
        "devices": devs,
        "count": len(devs),
        "source": "mock" if _mock_enabled() else "empty",
    })
    return jsonify(payload), 200


@bp.get("/telemetry/latest")
def telemetry_latest():
    """Mock telemetry. No real polling, no real agent. The shape mirrors
    the schema documented in `docs/TELEMETRY_SCHEMA.md` so the dashboard
    contract can stabilize before any real ingestion exists."""
    payload = _safety_envelope()
    if _mock_enabled():
        payload.update({
            "status": "mock",
            "device_id": "mock-mount-0",
            "kind": "mount",
            "sample": {
                "ts": _now_iso(),
                "ra_hours": 5.123,
                "dec_degrees": 12.345,
                "is_tracking": False,
            },
        })
    else:
        payload.update({
            "status": "not_connected",
            "device_id": None,
            "kind": None,
            "sample": None,
        })
    return jsonify(payload), 200
