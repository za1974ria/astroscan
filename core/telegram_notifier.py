"""
Envoi des notifications AstroScan vers Telegram (Bot API sendMessage).
Variables d’environnement : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import List

_log = logging.getLogger("astroscan.telegram")

# Timeout court — ne pas bloquer l’API si Telegram est lent ou injoignable
_SEND_TIMEOUT_SEC = 4.0


def send_telegram_notifications(notifications: List[str]) -> None:
    """
    Envoie chaque chaîne comme message distinct. Échecs silencieux (réseau, API, config manquante).
    """
    try:
        if not notifications:
            return
        token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
        if not token or not chat_id:
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"

        for msg in notifications:
            if not (msg or "").strip():
                continue
            try:
                body = json.dumps(
                    {"chat_id": chat_id, "text": str(msg)},
                    ensure_ascii=False,
                ).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                with urllib.request.urlopen(req, timeout=_SEND_TIMEOUT_SEC) as resp:
                    resp.read()
            except Exception as e:
                _log.debug("telegram sendMessage failed: %s", e)
    except Exception as e:
        _log.debug("telegram notifier: %s", e)
