# -*- coding: utf-8 -*-
"""Push notifications pour éruptions M/X — SQLite + pywebpush (optionnel)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

UA = {"User-Agent": "ASTRO-SCAN/1.0 orbital-chohra@gmail.com"}

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    webpush = None
    WebPushException = Exception  # type: ignore


def _db_path_push(base: str) -> str:
    return os.path.join(base, "data", "push_subscriptions.db")


def _db_path_alerts(base: str) -> str:
    return os.path.join(base, "data", "alerts_sent.db")


def _ensure_parent(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def init_subscription_db(base_dir: str) -> None:
    path = _db_path_push(base_dir)
    _ensure_parent(path)
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT UNIQUE NOT NULL,
                p256dh TEXT,
                auth TEXT,
                created_at REAL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def init_alerts_sent_db(base_dir: str) -> None:
    path = _db_path_alerts(base_dir)
    _ensure_parent(path)
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_flares (
                flare_id TEXT PRIMARY KEY,
                max_class TEXT,
                max_time TEXT,
                pushed_at REAL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_subscription(base_dir: str, sub: Dict[str, Any]) -> bool:
    endpoint = (sub.get("endpoint") or "").strip()
    if not endpoint:
        return False
    keys = sub.get("keys") or {}
    p256dh = keys.get("p256dh") or ""
    auth = keys.get("auth") or ""
    init_subscription_db(base_dir)
    path = _db_path_push(base_dir)
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
        conn.execute(
            "INSERT INTO subscriptions (endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?)",
            (endpoint, p256dh, auth, time.time()),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def list_subscriptions(base_dir: str) -> List[Dict[str, Any]]:
    path = _db_path_push(base_dir)
    if not os.path.isfile(path):
        return []
    conn = sqlite3.connect(path, timeout=30)
    try:
        rows = conn.execute("SELECT endpoint, p256dh, auth FROM subscriptions").fetchall()
        out = []
        for ep, p256, au in rows:
            out.append(
                {
                    "endpoint": ep,
                    "keys": {"p256dh": p256 or "", "auth": au or ""},
                }
            )
        return out
    finally:
        conn.close()


def flare_already_sent(base_dir: str, flare_id: str) -> bool:
    path = _db_path_alerts(base_dir)
    if not os.path.isfile(path):
        return False
    conn = sqlite3.connect(path, timeout=30)
    try:
        r = conn.execute("SELECT 1 FROM sent_flares WHERE flare_id = ?", (flare_id,)).fetchone()
        return r is not None
    finally:
        conn.close()


def mark_flare_sent(base_dir: str, flare_id: str, max_class: str, max_time: str) -> None:
    init_alerts_sent_db(base_dir)
    path = _db_path_alerts(base_dir)
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sent_flares (flare_id, max_class, max_time, pushed_at) VALUES (?, ?, ?, ?)",
            (flare_id, max_class, max_time, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_mx_class(max_class: str) -> Optional[str]:
    if not max_class or not isinstance(max_class, str):
        return None
    s = max_class.strip().upper()
    if len(s) < 1:
        return None
    letter = s[0]
    if letter not in ("M", "X"):
        return None
    return letter


def fetch_recent_mx_flares(max_age_hours: int = 48) -> List[Dict[str, Any]]:
    """Événements M/X récents (fenêtre max_age_hours) — GOES xray-flares-7-day."""
    from datetime import datetime, timedelta, timezone

    url = "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-7-day.json"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("solar_alert_worker: fetch flares %s", e)
        return []
    if not isinstance(data, list):
        return []
    cut = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    out = []
    for ev in data:
        if not isinstance(ev, dict):
            continue
        mc = ev.get("max_class") or ""
        if _parse_mx_class(mc) is None:
            continue
        mt = ev.get("max_time") or ev.get("begin_time")
        if not mt:
            continue
        try:
            t = datetime.fromisoformat(mt.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t < cut:
            continue
        out.append({"max_class": mc, "max_time": mt, "begin_time": ev.get("begin_time")})
    return out


def check_and_notify_mx_flares(base_dir: str) -> int:
    """
    Envoie une notification push pour chaque éruption M/X pas encore enregistrée.
    Retourne le nombre de notifications envoyées (tentatives).
    """
    if webpush is None:
        log.debug("solar_alert_worker: pywebpush absent, skip push")
        return 0
    priv = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    if not priv:
        log.debug("solar_alert_worker: VAPID_PRIVATE_KEY manquant, skip push")
        return 0
    mailto = (os.environ.get("VAPID_SUB") or "mailto:orbital-chohra@gmail.com").strip()
    if not mailto.startswith("mailto:"):
        mailto = "mailto:" + mailto

    subs = list_subscriptions(base_dir)
    if not subs:
        return 0

    sent_n = 0
    for ev in fetch_recent_mx_flares():
        mc = ev.get("max_class") or ""
        mt = ev.get("max_time") or ""
        fid = f"{mt}|{mc}"
        if flare_already_sent(base_dir, fid):
            continue
        title = "⚡ ÉRUPTION SOLAIRE DÉTECTÉE"
        body = f"Classe {mc} détectée — suivez la météo spatiale LIVE (impact possible Terre ~15–48 h selon CME)."
        payload = json.dumps(
            {"title": title, "body": body, "url": "/meteo-spatiale"},
            ensure_ascii=False,
        )
        vapid_claims = {"sub": mailto}
        ok_any = False
        for sub in subs:
            try:
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=priv,
                    vapid_claims=vapid_claims,
                    timeout=15,
                )
                ok_any = True
            except WebPushException as e:
                log.warning("webpush fail: %s", e)
                if getattr(e, "response", None) is not None and e.response is not None:
                    try:
                        if e.response.status_code in (404, 410):
                            _remove_subscription(base_dir, sub.get("endpoint"))
                    except Exception:
                        pass
            except Exception as e:
                log.warning("webpush error: %s", e)
        if ok_any:
            mark_flare_sent(base_dir, fid, mc, mt)
            sent_n += 1
            log.info("solar_alert_worker: notification envoyée pour %s", fid)
    return sent_n


def _remove_subscription(base_dir: str, endpoint: Optional[str]) -> None:
    if not endpoint:
        return
    path = _db_path_push(base_dir)
    if not os.path.isfile(path):
        return
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
        conn.commit()
    finally:
        conn.close()


def solar_alert_loop(base_dir: str, interval_s: int = 600, stop_event: Optional[threading.Event] = None) -> None:
    init_subscription_db(base_dir)
    init_alerts_sent_db(base_dir)
    time.sleep(25)
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            check_and_notify_mx_flares(base_dir)
        except Exception as e:
            log.warning("solar_alert_loop: %s", e)
        if stop_event is not None:
            if stop_event.wait(interval_s):
                break
        else:
            time.sleep(interval_s)
