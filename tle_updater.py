#!/usr/bin/env python3
"""
tle_updater.py — Mise à jour du catalogue TLE via SatNOGS
=========================================================
Remplace CelesTrak (bloqué depuis Hetzner) par SatNOGS qui
synchronise depuis Space-Track.org.

Met à jour deux fichiers :
  - data/tle/active.tle      (format 3 lignes standard)
  - data/tle_active_cache.json  (cache JSON lu par station_web.py)

Cron recommandé : 0 */6 * * * python3 /root/astro_scan/tle_updater.py
"""

import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone

import requests

STATION = "/root/astro_scan"
TLE_PATH = os.path.join(STATION, "data", "tle", "active.tle")
CACHE_PATH = os.path.join(STATION, "data", "tle_active_cache.json")
LOG_PATH = os.path.join(STATION, "logs", "tle_update.log")

SATNOGS_URL = "https://db.satnogs.org/api/tle/?format=json&satellite__status=alive"
ARISS_ISS_URL = "https://live.ariss.org/iss.txt"

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("tle_updater")


def fetch_satnogs(timeout=30):
    log.info("Fetching TLE catalogue from SatNOGS...")
    r = requests.get(SATNOGS_URL, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected SatNOGS response type: {type(data)}")
    log.info("Received %d satellites from SatNOGS", len(data))
    return data


def fetch_iss_ariss(timeout=10):
    """Récupère le TLE ISS temps réel depuis ARISS (toujours accessible)."""
    try:
        r = requests.get(ARISS_ISS_URL, timeout=timeout)
        r.raise_for_status()
        lines = [ln.strip() for ln in r.text.splitlines() if ln.strip()]
        # Cherche le triplet ISS
        for i in range(len(lines) - 2):
            if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
                return {"name": lines[i], "tle1": lines[i + 1], "tle2": lines[i + 2]}
    except Exception as e:
        log.warning("ARISS ISS fetch failed: %s", e)
    return None


def normalize(item):
    """Convertit un enregistrement SatNOGS en dict homogène."""
    tle0_raw = item.get("tle0") or ""
    name = (tle0_raw[2:] if tle0_raw.startswith("0 ") else tle0_raw).strip()
    line1 = (item.get("tle1") or "").strip()
    line2 = (item.get("tle2") or "").strip()
    if not name or not line1.startswith("1 ") or not line2.startswith("2 "):
        return None
    return {
        "name": name,
        "norad_cat_id": item.get("norad_cat_id"),
        "tle_line1": line1,
        "tle_line2": line2,
        "object_type": None,
        "epoch": item.get("updated"),
    }


def build_catalogue(satnogs_data, iss_override=None):
    """Construit la liste normalisée, avec ISS ARISS en priorité."""
    items = []
    iss_norad = 25544
    for raw in satnogs_data:
        norm = normalize(raw)
        if norm is None:
            continue
        # On remplacera l'ISS par la version ARISS si disponible
        if iss_override and norm.get("norad_cat_id") == iss_norad:
            continue
        items.append(norm)

    if iss_override:
        iss_item = {
            "name": iss_override["name"],
            "norad_cat_id": iss_norad,
            "tle_line1": iss_override["tle1"],
            "tle_line2": iss_override["tle2"],
            "object_type": "PAYLOAD",
            "epoch": datetime.now(timezone.utc).isoformat(),
        }
        items.insert(0, iss_item)
        log.info("ISS TLE injected from ARISS")

    return items


def write_atomic(path, content):
    dir_ = os.path.dirname(path)
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tle_update_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def items_to_tle_text(items):
    """Convertit la liste en format 3 lignes standard."""
    lines = []
    for item in items:
        lines.append(item["name"])
        lines.append(item["tle_line1"])
        lines.append(item["tle_line2"])
    return "\n".join(lines) + "\n"


def items_to_cache_json(items):
    """Construit le dict JSON compatible avec load_tle_cache_from_disk()."""
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "status": "connected",
        "source": "SatNOGS via Space-Track.org",
        "last_refresh_iso": ts,
        "count": len(items),
        "items": items,
        "error": None,
    }


def main():
    try:
        satnogs_data = fetch_satnogs()
    except Exception as e:
        log.error("SatNOGS fetch failed: %s", e)
        print(f"ERREUR SatNOGS: {e}", file=sys.stderr)
        sys.exit(1)

    iss_live = fetch_iss_ariss()
    items = build_catalogue(satnogs_data, iss_override=iss_live)

    if not items:
        log.error("No valid TLE items built — aborting write")
        sys.exit(1)

    tle_text = items_to_tle_text(items)
    cache_dict = items_to_cache_json(items)

    try:
        write_atomic(TLE_PATH, tle_text)
        log.info("active.tle updated: %d objects", len(items))
    except Exception as e:
        log.error("active.tle write failed: %s", e)
        print(f"ERREUR écriture active.tle: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        write_atomic(CACHE_PATH, json.dumps(cache_dict, ensure_ascii=False, indent=2))
        log.info("tle_active_cache.json updated: %d objects", len(items))
    except Exception as e:
        log.warning("tle_active_cache.json write failed (non-fatal): %s", e)

    print(f"OK: {len(items)} TLE écrits — source: SatNOGS / ISS: {'ARISS live' if iss_live else 'SatNOGS'}")


if __name__ == "__main__":
    main()
