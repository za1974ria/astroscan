"""Service security — rate-limiting + extraction IP cliente + décorateurs admin/RL.

PASS 2D Cat 5 (2026-05-07) : extraction depuis station_web.py de
  - `_api_rate_limit_allow` (fenêtre glissante anti-abus, thread-safe)
  - `_client_ip_from_request` (X-Forwarded-For / remote_addr)
  - Globals `_API_RATE_LOCK`, `_API_RATE_HITS` (état interne)

PASS 28.SEC (2026-05-09) : ajout
  - `require_admin` (décorateur fail-closed via ADMIN_TOKEN env)
  - `rate_limit_ip` (décorateur process-local, fenêtre 60s glissante)

Limites connues du rate-limiter
-------------------------------
Le compteur est process-local (mémoire du worker gunicorn). Avec 4 workers,
un client peut effectivement émettre 4× la limite avant d'être bloqué partout.
Suffisant pour la phase actuelle (anti-drainage IA, anti-troll DB), pas
suffisant pour un rate-limit strict global → migrer vers Redis si besoin.
"""
from __future__ import annotations

import functools
import logging
import os
import threading
import time

from flask import request

from app.utils.responses import api_error


_API_RATE_LOCK = threading.Lock()
_API_RATE_HITS: dict[str, list[float]] = {}

_log_sec = logging.getLogger("astroscan.security")


def _api_rate_limit_allow(key: str, limit: int, window_sec: int) -> tuple[bool, int]:
    """
    Fenêtre glissante simple anti-abus.
    Retourne (allowed, retry_after_sec).
    """
    now = time.time()
    try:
        with _API_RATE_LOCK:
            hits = _API_RATE_HITS.get(key, [])
            cutoff = now - float(window_sec)
            hits = [t for t in hits if t >= cutoff]
            if len(hits) >= int(limit):
                retry_after = max(1, int(window_sec - (now - hits[0])))
                _API_RATE_HITS[key] = hits
                return False, retry_after
            hits.append(now)
            _API_RATE_HITS[key] = hits
            # Garde-fou mémoire (rare)
            if len(_API_RATE_HITS) > 8000:
                for k in list(_API_RATE_HITS.keys())[:1500]:
                    arr = _API_RATE_HITS.get(k) or []
                    if not arr or arr[-1] < now - 3600:
                        _API_RATE_HITS.pop(k, None)
            return True, 0
    except Exception:
        return True, 0


def _client_ip_from_request(req):
    """Extrait l'IP client (X-Forwarded-For en priorité, sinon remote_addr)."""
    ip = req.headers.get("X-Forwarded-For", req.remote_addr or "")
    ip = (ip or "").split(",")[0].strip()
    return ip


def _admin_token_expected() -> str:
    """Token admin attendu. Préfère ADMIN_TOKEN, retombe sur ASTROSCAN_ADMIN_TOKEN.

    Retourne chaîne vide si rien n'est configuré (fail-closed côté décorateur).
    """
    return (
        os.environ.get("ADMIN_TOKEN")
        or os.environ.get("ASTROSCAN_ADMIN_TOKEN")
        or ""
    ).strip()


def _extract_admin_token(req) -> str:
    """Lit le token côté requête : X-Admin-Token prioritaire, fallback Authorization: Bearer."""
    tok = (req.headers.get("X-Admin-Token") or "").strip()
    if tok:
        return tok
    auth = (req.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def require_admin(f):
    """Vérifie le header X-Admin-Token (ou Authorization: Bearer) contre ADMIN_TOKEN env.

    - Fail-closed : si ADMIN_TOKEN/ASTROSCAN_ADMIN_TOKEN n'est pas défini en env,
      l'endpoint est refusé pour tout le monde (503).
    - Réponse 401 + log warning si token absent/invalide.
    - Réponse JSON standardisée via api_error().
    """
    @functools.wraps(f)
    def _wrapper(*args, **kwargs):
        expected = _admin_token_expected()
        client_ip = _client_ip_from_request(request)
        if not expected:
            _log_sec.warning(
                "admin_endpoint_disabled endpoint=%s ip=%s reason=ADMIN_TOKEN_unset",
                request.endpoint, client_ip,
            )
            return api_error(
                "Admin endpoint disabled (ADMIN_TOKEN not configured)",
                code=503,
            )
        provided = _extract_admin_token(request)
        if not provided or provided != expected:
            _log_sec.warning(
                "admin_unauthorized endpoint=%s ip=%s has_token=%s",
                request.endpoint, client_ip, bool(provided),
            )
            return api_error("Unauthorized", code=401)
        return f(*args, **kwargs)
    return _wrapper


def rate_limit_ip(max_per_minute: int = 10, key_prefix: str | None = None):
    """Rate-limit en mémoire process-local, fenêtre glissante 60s.

    - Clé : (key_prefix or request.endpoint, client_ip).
    - Headers ajoutés à toutes les réponses : X-RateLimit-Limit,
      X-RateLimit-Remaining, X-RateLimit-Reset.
    - Renvoie 429 + Retry-After + log info si dépassé.
    - Process-local : chaque worker gunicorn a son compteur (4 workers
      ⇒ effectif ≈ 4 × max_per_minute). Acceptable pour la phase actuelle.

    Usage:
        @bp.route("/api/foo", methods=["POST"])
        @rate_limit_ip(max_per_minute=10)
        def foo(): ...
    """
    window_sec = 60

    def _decorator(f):
        @functools.wraps(f)
        def _wrapper(*args, **kwargs):
            ip = _client_ip_from_request(request) or "unknown"
            prefix = key_prefix or (request.endpoint or f.__name__)
            key = f"rl:{prefix}:{ip}"
            allowed, retry_after = _api_rate_limit_allow(
                key, max_per_minute, window_sec
            )
            # Compteur courant (post-incrément si autorisé) pour les headers
            with _API_RATE_LOCK:
                hits = _API_RATE_HITS.get(key, [])
                used = len(hits)
            remaining = max(0, max_per_minute - used)
            if not allowed:
                _log_sec.info(
                    "rate_limit_block prefix=%s ip=%s limit=%d retry_after=%d",
                    prefix, ip, max_per_minute, retry_after,
                )
                resp, code = api_error(
                    "Rate limit exceeded — retry later",
                    code=429,
                    retry_after=retry_after,
                    limit=max_per_minute,
                    window_sec=window_sec,
                )
                resp.headers["Retry-After"] = str(retry_after)
                resp.headers["X-RateLimit-Limit"] = str(max_per_minute)
                resp.headers["X-RateLimit-Remaining"] = "0"
                resp.headers["X-RateLimit-Reset"] = str(retry_after)
                return resp, code

            rv = f(*args, **kwargs)
            try:
                # Flask peut renvoyer Response, tuple (Response, code), tuple (str, code)…
                if isinstance(rv, tuple):
                    body = rv[0]
                else:
                    body = rv
                if hasattr(body, "headers"):
                    body.headers["X-RateLimit-Limit"] = str(max_per_minute)
                    body.headers["X-RateLimit-Remaining"] = str(remaining)
                    body.headers["X-RateLimit-Reset"] = str(window_sec)
            except Exception:
                pass
            return rv
        return _wrapper
    return _decorator
