"""Shared security decorators for the AstroBrain + Guardian blueprints.

Single rule for Session 1: BOTH the socket peer AND the absence of any
proxy header must hold. This means an endpoint protected by @require_localhost:

    - Refuses any non-loopback request.remote_addr (403).
    - Refuses any request bearing X-Forwarded-For or X-Real-IP (would mean
      Nginx forwarded it — that exposes us publicly).

This is intentionally stricter than a single check. It guarantees that even
if someone later adds `location /api/astrobrain/* { proxy_pass ... }` to
Nginx without thinking, the endpoint stays inaccessible until the new
auth design lands in Session 2.
"""
from __future__ import annotations

import logging
from functools import wraps

from flask import jsonify, request

log = logging.getLogger(__name__)

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def is_localhost_request() -> tuple[bool, str]:
    """Return (allowed, reason). Pure function, easy to unit test."""
    ra = (request.remote_addr or "").strip()
    if ra not in _LOOPBACK:
        return False, f"non_loopback_peer:{ra or 'empty'}"
    if request.headers.get("X-Forwarded-For"):
        return False, "x_forwarded_for_present"
    if request.headers.get("X-Real-IP"):
        return False, "x_real_ip_present"
    return True, "ok"


def require_localhost(fn):
    """Flask view decorator — 403 unless caller is on the loopback interface
    AND no proxy headers are present.

    This blocks public exposure even if Nginx is misconfigured to forward
    the path. Pair with localhost-only systemd / firewall in Session 2.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        ok, reason = is_localhost_request()
        if not ok:
            log.warning(
                "[localhost-guard] refused on path=%s reason=%s peer=%s",
                request.path, reason, request.remote_addr,
            )
            return jsonify({"ok": False, "error": "localhost_only"}), 403
        return fn(*args, **kwargs)
    return wrapper


__all__ = ["is_localhost_request", "require_localhost"]
