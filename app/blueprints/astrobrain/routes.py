"""AstroBrain HTTP routes — all localhost-only.

Routes:
    POST /api/astrobrain/ask                — free-form question
    POST /api/astrobrain/explain-telemetry  — interpret a telemetry JSON
    GET  /api/astrobrain/health             — service self-status

The url_prefix '/api/astrobrain' is applied at registration (app/__init__.py).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from app.blueprints.astrobrain import rate_limit
from app.blueprints.astrobrain.security import require_localhost
from app.blueprints.astrobrain.service import AstroBrainService

log = logging.getLogger(__name__)

bp = Blueprint("astrobrain", __name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ACCESS_LOG = _PROJECT_ROOT / "logs" / "astrobrain" / "access.log"


def _access_log(status: int, latency_ms: int, extra: dict | None = None) -> None:
    """Append an access log line (no payload, no secrets)."""
    try:
        _ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "path": request.path,
            "remote_addr": request.remote_addr,
            "status": status,
            "latency_ms": latency_ms,
        }
        if extra:
            entry.update(extra)
        with open(_ACCESS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Access logging must never break the request path.
        pass


def _get_service() -> AstroBrainService:
    """Lazy singleton attached to current_app to avoid re-creating LLMClient per request."""
    svc = current_app.extensions.get("astrobrain_service") if current_app else None
    if svc is None:
        svc = AstroBrainService()
        if current_app:
            current_app.extensions["astrobrain_service"] = svc
    return svc


# ─── Routes ─────────────────────────────────────────────────────────────────


@bp.route("/ask", methods=["POST"])
@require_localhost
def api_ask():
    t0 = time.monotonic()
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}

    question = payload.get("question")
    context = payload.get("context")
    if not isinstance(question, str) or not question.strip():
        latency_ms = int((time.monotonic() - t0) * 1000)
        _access_log(400, latency_ms, {"reason": "question_required"})
        return jsonify({"ok": False, "error": "question_required"}), 400
    if len(question) > 4000:
        latency_ms = int((time.monotonic() - t0) * 1000)
        _access_log(413, latency_ms, {"reason": "question_too_long"})
        return jsonify({"ok": False, "error": "question_too_long", "max_chars": 4000}), 413
    if context is not None and not isinstance(context, dict):
        latency_ms = int((time.monotonic() - t0) * 1000)
        _access_log(400, latency_ms, {"reason": "context_must_be_object"})
        return jsonify({"ok": False, "error": "context_must_be_object"}), 400

    result = _get_service().ask(question, context=context)
    status = 200 if result.get("ok") else (
        429 if result.get("error") == "daily_token_budget_exceeded" else 502
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    _access_log(status, latency_ms, {"method": "ask", "dry_run": result.get("dry_run")})
    return jsonify(result), status


@bp.route("/explain-telemetry", methods=["POST"])
@require_localhost
def api_explain_telemetry():
    t0 = time.monotonic()
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}

    telemetry = payload.get("telemetry")
    focus = payload.get("focus")
    if not isinstance(telemetry, dict) or not telemetry:
        latency_ms = int((time.monotonic() - t0) * 1000)
        _access_log(400, latency_ms, {"reason": "telemetry_required"})
        return jsonify({"ok": False, "error": "telemetry_required"}), 400
    if focus is not None and not isinstance(focus, str):
        latency_ms = int((time.monotonic() - t0) * 1000)
        _access_log(400, latency_ms, {"reason": "focus_must_be_string"})
        return jsonify({"ok": False, "error": "focus_must_be_string"}), 400

    result = _get_service().explain_telemetry(telemetry, focus=focus)
    status = 200 if result.get("ok") else (
        429 if result.get("error") == "daily_token_budget_exceeded" else 502
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    _access_log(status, latency_ms, {"method": "explain_telemetry", "dry_run": result.get("dry_run")})
    return jsonify(result), status


@bp.route("/health", methods=["GET"])
@require_localhost
def api_health():
    """Self-status — does NOT make an LLM call. Cheap & safe to poll."""
    t0 = time.monotonic()
    key_present = bool((os.environ.get("OPENAI_API_KEY") or "").strip())
    dry_run = os.environ.get("LLM_DRY_RUN", "0").strip() in ("1", "true", "True", "yes") or not key_present
    snap = rate_limit.status()

    body = {
        "ok": True,
        "module": "astrobrain",
        "version": "1.0.0",
        "openai_key_present": key_present,
        "dry_run": dry_run,
        "model_default": (os.environ.get("ASTROBRAIN_MODEL_DEFAULT") or "gpt-5-mini").strip(),
        "model_premium": (os.environ.get("ASTROBRAIN_MODEL_PREMIUM") or "gpt-5").strip(),
        "budget": snap,
    }
    latency_ms = int((time.monotonic() - t0) * 1000)
    _access_log(200, latency_ms, {"method": "health"})
    return jsonify(body), 200
