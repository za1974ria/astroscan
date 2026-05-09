"""PASS 23.2 (2026-05-08) — Logging service (foundation).

Extrait depuis station_web.py:509-662 lors de PASS 23.2.

Ce module contient :
- Throttling state pour anti-spam http_request logs (token bucket)
- ``_http_request_log_allow()`` : décide si on log une requête 2xx/3xx
- ``struct_log(level, **fields)`` : logger structuré JSON (filtrable par
  category/event), feed errors_last_5min via metrics_service
- ``system_log(message)`` : alias logger ``orbital_system``
- ``_health_log_error(component, message, severity)`` : tracking d'erreurs
  santé pour /status (mute station_web.HEALTH_STATE.last_error)
- ``_health_set_error()`` : alias rétro-compat

Dépendances inverses :
- ``struct_log`` lazy-importe ``metrics_record_struct_error`` depuis
  ``app.services.metrics_service`` (dépendance fonctionnelle, pas un
  cycle au load grâce au lazy import)
- ``_health_log_error`` lazy-importe ``HEALTH_STATE`` et ``log`` depuis
  ``station_web`` (cycle-safe car appelé post-init)
- ``system_log`` lazy-importe ``_orbital_log`` depuis ``station_web``

Mutables globals (token bucket state) :
- ``_HTTP_LOG_TOKENS``, ``_HTTP_LOG_LAST_MONO`` sont réassignés dans
  ``_http_request_log_allow`` via ``global`` keyword. Le ``global``
  mute le namespace de **ce module** (logging_service), pas station_web.
  Aucun consommateur externe n'utilise ces 2 variables → pas de
  divergence silencieuse possible.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

# ── HTTP request log throttling (token bucket anti-spam) ─────────────
# Jeton : limite le volume de logs JSON "http_request" sous fort trafic
# (stabilité I/O). Réassignés au runtime → restent dans CE module.
_HTTP_LOG_LOCK = threading.Lock()
_HTTP_LOG_TOKENS: float = 5.0
_HTTP_LOG_MAX: float = 8.0
_HTTP_LOG_REFILL_PER_SEC: float = 3.0
_HTTP_LOG_LAST_MONO: float = time.monotonic()


def _http_request_log_allow() -> bool:
    """True si on peut émettre un struct_log pour une requête 2xx/3xx (anti-spam)."""
    try:
        with _HTTP_LOG_LOCK:
            global _HTTP_LOG_TOKENS, _HTTP_LOG_LAST_MONO
            m = time.monotonic()
            dt = max(0.0, m - _HTTP_LOG_LAST_MONO)
            _HTTP_LOG_LAST_MONO = m
            _HTTP_LOG_TOKENS = min(_HTTP_LOG_MAX, _HTTP_LOG_TOKENS + dt * _HTTP_LOG_REFILL_PER_SEC)
            if _HTTP_LOG_TOKENS >= 1.0:
                _HTTP_LOG_TOKENS -= 1.0
                return True
            return False
    except Exception:
        return True


def struct_log(level: int, **fields) -> None:
    """
    Écrit une ligne structurée dans astroscan_structured.log (via logger racine).
    Utiliser category/event pour filtrer (api, tle, error, ...).
    Les ERROR alimentent errors_last_5min pour /status.
    """
    try:
        if level >= logging.ERROR:
            # Lazy import : évite cycle au load (metrics_service standalone).
            from app.services.metrics_service import metrics_record_struct_error
            metrics_record_struct_error()
        lg = logging.getLogger("astroscan")
        msg = str(fields.get("event") or fields.get("msg") or "event")
        lg.log(level, msg, extra={"astroscan_extra": dict(fields)})
    except Exception:
        pass


def system_log(message) -> None:
    """Log via le logger 'orbital_system' (handler RotatingFileHandler géré dans station_web)."""
    # Lazy import : _orbital_log est attaché à un handler de rotation initialisé
    # dans station_web.py l.404 — on garde le binding canonique côté monolith.
    from station_web import _orbital_log
    _orbital_log.info(message)


def _health_log_error(component: str, message: str, severity: str = "warn") -> None:
    """
    Structured health error logger.
    - component: short identifier
    - message: human readable
    - severity: info|warn|error|critical
    Maintains a last_error snapshot for /status.
    """
    # Lazy imports : HEALTH_STATE et log sont définis dans station_web.
    # Au moment où cette fonction est appelée (post-init), ils sont disponibles.
    try:
        from datetime import datetime, timezone
        from station_web import HEALTH_STATE

        sev = (severity or "warn").lower()
        sev = sev if sev in ("info", "warn", "error", "critical") else "warn"
        err = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "component": component,
            "message": str(message),
            "severity": sev,
        }
        HEALTH_STATE["last_error"] = err
        # log using python logging levels (best effort)
        try:
            if sev in ("error", "critical"):
                log.error("HEALTH[%s] %s: %s", component, sev, message)
            elif sev == "warn":
                log.warning("HEALTH[%s] %s: %s", component, sev, message)
            else:
                log.info("HEALTH[%s] %s: %s", component, sev, message)
        except Exception:
            pass
        try:
            lvl = (
                logging.ERROR
                if sev in ("error", "critical")
                else (logging.WARNING if sev == "warn" else logging.INFO)
            )
            struct_log(
                lvl,
                category="health",
                event="health_signal",
                component=component,
                severity=sev,
                message=str(message)[:800],
            )
        except Exception:
            pass
    except Exception:
        pass


def _health_set_error(component: str, message: str, severity: str = "warn") -> None:
    """Backward-compatible alias for earlier calls."""
    _health_log_error(component, message, severity)


__all__ = [
    "_http_request_log_allow",
    "struct_log",
    "system_log",
    "_health_log_error",
    "_health_set_error",
]
