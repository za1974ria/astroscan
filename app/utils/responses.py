"""Standard API response format — PASS 28.

Helpers for new endpoints to use a consistent response envelope.

EXISTING endpoints are NOT migrated to this format (backward-compat).
ONLY NEW code created after PASS 28 should use api_ok / api_error.

Usage:
    from app.utils.responses import api_ok, api_error
    return api_ok({"foo": "bar"})
    return api_error("Invalid input", code=400)
"""
from datetime import datetime, timezone
from flask import jsonify


def api_ok(data=None, **extra):
    """Standard success envelope.

    Returns:
        Flask response with shape:
        {"ok": true, "data": ..., "timestamp": "2026-...", ...extra}
    """
    payload = {
        "ok": True,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(extra)
    return jsonify(payload)


def api_error(message, code=400, **extra):
    """Standard error envelope.

    Args:
        message: human-readable error description
        code: HTTP status code (default 400)
        **extra: optional fields like 'detail', 'field', etc.

    Returns:
        Tuple (Flask response, HTTP code)
    """
    payload = {
        "ok": False,
        "error": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(extra)
    return jsonify(payload), code
