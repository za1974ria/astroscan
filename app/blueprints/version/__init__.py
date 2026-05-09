"""Blueprint version — Public build-info endpoint for monitoring & CTO checks.

Created in PASS 28 (2026-05-04).
Exposes /api/build: commit hash, branch, boot time. Cached at first call.

NOTE: The original prompt asked for /api/version, but that route already
exists in the api_docs blueprint (returns name/version/status). To respect
"DO NOT break existing routes/contracts", this blueprint exposes the
build info under /api/build instead.
"""
import os
import subprocess
from datetime import datetime, timezone
from flask import Blueprint, jsonify, make_response

bp = Blueprint("version", __name__)

_BUILD_INFO = None


def _resolve_build_info():
    global _BUILD_INFO
    if _BUILD_INFO is not None:
        return _BUILD_INFO
    station_path = os.environ.get("STATION", "/root/astro_scan")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=station_path,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
    except Exception:
        commit = "unknown"
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=station_path,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
    except Exception:
        branch = "unknown"
    _BUILD_INFO = {
        "version": "2.0",
        "phase": "Phase 2C + Security hardened",
        "commit": commit,
        "branch": branch,
        "boot_time": datetime.now(timezone.utc).isoformat(),
    }
    return _BUILD_INFO


@bp.route("/api/build")
def build():
    """Public build info — useful for monitoring & due diligence.

    Cached client-side for 5 minutes (PASS 29) since build info changes
    only on deploy. The subprocess that resolves git metadata already
    runs only once per worker via the in-process cache.
    """
    resp = make_response(jsonify({
        "ok": True,
        **_resolve_build_info(),
    }))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp
