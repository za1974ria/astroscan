"""
Alertes dérivées du cache système uniquement (aucun réseau).
Utilise build_system_status_cache_payload() — log disque data_core/alerts/alerts.log.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List


def _alerts_dir(station_root: str) -> str:
    return os.path.join(station_root, "data_core", "alerts")


def _alerts_log_path(station_root: str) -> str:
    return os.path.join(_alerts_dir(station_root), "alerts.log")


def _log_lines_for_alert(ts: str, alert: Dict[str, Any]) -> str:
    """Format lignes bonus : [UTC] LEVEL module message (raccourcis demandés)."""
    level = (alert.get("level") or "info").upper()
    mod = alert.get("module") or "global"
    msg = (alert.get("message") or "").strip()

    if level == "CRITICAL" and mod == "dsn" and "Fallback" in msg:
        return f"[{ts}] CRITICAL dsn fallback et redemarre le systheme proprement\n"

    if level == "WARNING" and msg == "Data is stale":
        return f"[{ts}] WARNING {mod} stale\n"

    return f"[{ts}] {level} {mod} {msg}\n"


def _append_alerts_log(station_root: str, alerts: List[Dict[str, Any]]) -> None:
    if not alerts:
        return
    d = _alerts_dir(station_root)
    os.makedirs(d, exist_ok=True)
    path = _alerts_log_path(station_root)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(path, "a", encoding="utf-8") as f:
            for a in alerts:
                f.write(_log_lines_for_alert(ts, a))
    except OSError:
        pass


def analyze_system_alerts(station_root: str) -> Dict[str, Any]:
    from core.system_status_engine import build_system_status_cache_payload

    status = build_system_status_cache_payload(station_root)
    alerts: List[Dict[str, Any]] = []

    if status.get("global_status") == "critical":
        alerts.append(
            {
                "level": "critical",
                "message": "System critical failure",
            }
        )

    for module in ("dsn", "weather", "skyview"):
        m = status.get(module) or {}

        if m.get("status") == "fallback":
            alerts.append(
                {
                    "level": "critical",
                    "module": module,
                    "message": "Fallback mode active",
                }
            )

        elif m.get("status") == "cache":
            alerts.append(
                {
                    "level": "warning",
                    "module": module,
                    "message": "Using cached data",
                }
            )

        if m.get("stale"):
            alerts.append(
                {
                    "level": "warning",
                    "module": module,
                    "message": "Data is stale",
                }
            )

    out: Dict[str, Any] = {
        "alerts": alerts,
        "count": len(alerts),
        "global_status": status.get("global_status", "unknown"),
    }

    try:
        os.makedirs(_alerts_dir(station_root), exist_ok=True)
    except OSError:
        pass
    _append_alerts_log(station_root, alerts)
    return out
