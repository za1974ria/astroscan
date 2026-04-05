"""
Notifications utilisateur dérivées des alertes cache (alert_engine uniquement).
Futur : Telegram, SMTP, webhook — extension prévue ici.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List


def _notifications_dir(station_root: str) -> str:
    return os.path.join(station_root, "data_core", "notifications")


def _notifications_log_path(station_root: str) -> str:
    return os.path.join(_notifications_dir(station_root), "notifications.log")


def _append_notifications_log(station_root: str, notifications: List[str]) -> None:
    if not notifications:
        return
    try:
        os.makedirs(_notifications_dir(station_root), exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path = _notifications_log_path(station_root)
        with open(path, "a", encoding="utf-8") as f:
            for n in notifications:
                f.write(f"[{ts}] {n}\n")
    except OSError:
        pass


def check_and_notify(station_root: str) -> Dict[str, Any]:
    from core import alert_engine as _alert_engine

    alerts = _alert_engine.analyze_system_alerts(station_root)
    notifications: List[str] = []

    for alert in alerts.get("alerts") or []:
        if alert.get("level") == "critical":
            notifications.append(
                f"CRITICAL: {alert.get('module', 'system')} issue"
            )
        elif alert.get("level") == "warning":
            notifications.append(
                f"WARNING: {alert.get('module', 'system')} degraded"
            )

    out: Dict[str, Any] = {
        "notifications": notifications,
        "count": len(notifications),
    }

    _append_notifications_log(station_root, notifications)

    if notifications:
        try:
            from core import telegram_notifier as _telegram_notifier

            _telegram_notifier.send_telegram_notifications(notifications)
        except Exception:
            pass

    return out
