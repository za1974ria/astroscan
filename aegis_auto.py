#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aegis_auto.py

Script autonome déclenchable via cron :

0 * * * * python3 /root/astro_scan/aegis_auto.py >> /root/astro_scan/logs/aegis_auto.log 2>&1

Il tourne en local et appelle les endpoints déjà exposés par station_web :
- /api/skyview/fetch  pour récupérer une image SkyView
- /api/chat           pour générer un rapport AEGIS (Gemini)

Rotation de 12 cibles basée sur l’heure UTC.
"""
import json
import sys
from datetime import datetime, timezone
from urllib import request, error

BASE = "http://localhost:5000"

ROTATION = [
    ("M42", "DSS2 Red"),
    ("M31", "2MASS-K"),
    ("M1", "DSS2 Red"),
    ("M51", "GALEX Near UV"),
    ("M57", "DSS2 Red"),
    ("M87", "DSS2 Red"),
    ("M104", "DSS2 Red"),
    ("M27", "2MASS-K"),
    ("M45", "DSS2 Red"),
    ("M13", "DSS2 Red"),
    ("M81", "WISE 3.4"),
    ("M22", "DSS2 Red"),
]


def _post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except error.URLError as e:
        print(f"[AEGIS_AUTO] HTTP error on {path}: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


def main():
    now = datetime.now(timezone.utc)
    hour = now.hour
    target, survey = ROTATION[hour % len(ROTATION)]

    print(f"[AEGIS_AUTO] {now.isoformat()} — cible {target} / {survey}")

    # 1) Capture SkyView
    resp = _post(
        "/api/skyview/fetch",
        {"target": target, "survey": survey, "pixels": 400},
    )
    if not resp.get("ok"):
        print(f"[AEGIS_AUTO] capture échouée: {resp.get('error')}")
        return

    size_kb = resp.get("size_kb")
    print(f"[AEGIS_AUTO] Image capturée: {resp.get('url_local')} ({size_kb} KB)")

    # 2) Rapport AEGIS via /api/chat (logique déjà dans station_web)
    prompt = (
        f"AEGIS AUTO: Analyse scientifique de {target} — {resp.get('target_name')} "
        f"— survey {resp.get('survey')}. "
        "Rapport structuré en 3 parties: [OBJET] [SURVEY] [ANOMALIE / POINTS REMARQUABLES]."
    )
    resp2 = _post("/api/chat", {"message": prompt})
    if resp2.get("ok") is False:
        print(f"[AEGIS_AUTO] rapport échoué: {resp2.get('error')}")
    else:
        print("[AEGIS_AUTO] Rapport AEGIS généré.")


if __name__ == "__main__":
    main()

