"""PASS 21.2 (2026-05-08) — TLE collector thread.

Extrait depuis station_web.py:4121-4305 lors de PASS 21.2.

Ce module regroupe les 5 fonctions liées au collector TLE :

- ``download_tle_now()`` — téléchargement rapide ARISS/Celestrak au boot
  (utilisé par ``app/bootstrap.py`` ou la routine d'init monolith).
- ``refresh_tle_from_amsat()`` — fusion AMSAT nasabare + ARISS ISS, met à
  jour ``data/tle/active.tle`` puis le cache mémoire ``TLE_CACHE``.
- ``_download_tle_catalog()`` — variante simple (ARISS uniquement).
- ``_run_tle_download_once()`` — appelle ``refresh_tle_from_amsat()`` puis
  re-programme un ``threading.Timer`` toutes les 6 heures.
- ``_start_tle_collector()`` — point d'entrée du thread, lancé par
  ``app/bootstrap.py:70`` via le shim ``from station_web import
  _start_tle_collector``. Lance un thread daemon qui sleep 60 s puis
  bascule sur ``_run_tle_download_once`` (auto-rescheduling).

Architecture rappelée :
- Pas de pattern leader/standby (à confirmer en relisant le code) :
  c'est un simple thread daemon par worker Gunicorn. Si plusieurs
  workers tournent, chacun déclenche son propre cycle de refresh ; les
  écritures sur ``data/tle/active.tle`` sont concurrentes mais idempotentes
  (dernière écriture gagne, contenu identique côté providers).
- ``TLE_CACHE`` est mutable identity-stable (cf. docstring de
  ``app/services/tle_cache.py``). Toute mise à jour passe par
  ``TLE_CACHE.update(...)`` ou ``TLE_CACHE.clear(); TLE_CACHE[...] = ...``.

Lazy imports inside les fonctions pour éviter le cycle station_web ↔
tle_collector au load (les fonctions sont appelées post-bootstrap).
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request
from datetime import datetime, timezone


def download_tle_now():
    """Download Celestrak active TLE at startup so /api/satellites/tle has real data."""
    from app.services.tle_cache import TLE_ACTIVE_PATH
    from station_web import log

    url = "https://live.ariss.org/iss.txt"
    try:
        try:
            import requests
            r = requests.get(url, timeout=3)
            if r.status_code == 200 and len(r.text) > 1000:
                with open(TLE_ACTIVE_PATH, "w", encoding="utf-8") as f:
                    f.write(r.text)
                log.info("TLE downloaded at startup.")
                if os.path.isfile(TLE_ACTIVE_PATH):
                    log.info("TLE FILE SIZE: %s", os.path.getsize(TLE_ACTIVE_PATH))
        except ImportError:
            req = urllib.request.Request(url, headers={"User-Agent": "AstroScan/1.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                text = r.read().decode("utf-8", errors="replace")
                if len(text) > 1000:
                    with open(TLE_ACTIVE_PATH, "w", encoding="utf-8") as f:
                        f.write(text)
                    log.info("TLE downloaded at startup.")
                    if os.path.isfile(TLE_ACTIVE_PATH):
                        log.info("TLE FILE SIZE: %s", os.path.getsize(TLE_ACTIVE_PATH))
    except Exception as e:
        log.warning("TLE download failed: %s", e)


def refresh_tle_from_amsat():
    """
    Refresh TLE from AMSAT + ARISS:
    1) Download AMSAT nasabare.txt
    2) Merge new 3-line TLE blocks into data/tle/active.tle
    3) Update ISS block from live.ariss.org/iss.txt
    4) If success, expose LIVE mode/state
    """
    from app.services.tle_cache import TLE_ACTIVE_PATH, TLE_CACHE, _parse_tle_file
    from station_web import HEALTH_STATE, log

    def _read_url_text(url, timeout=8):
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")

    def _parse_tle_triplets(text):
        out = []
        lines = [ln.strip() for ln in (text or "").splitlines() if ln and ln.strip()]
        i = 0
        while i + 2 < len(lines):
            name = lines[i].strip()
            l1 = lines[i + 1].strip()
            l2 = lines[i + 2].strip()
            if l1.startswith("1 ") and l2.startswith("2 "):
                out.append({"name": name or "Unknown", "line1": l1, "line2": l2})
                i += 3
                continue
            i += 1
        return out

    try:
        # Existing base file content
        existing = _parse_tle_file(TLE_ACTIVE_PATH) if os.path.isfile(TLE_ACTIVE_PATH) else []
        existing_map = {}
        for s in existing:
            key = (s.get("name", "").strip().upper(), s.get("line1", "").strip(), s.get("line2", "").strip())
            existing_map[key] = s

        # 1) AMSAT feed
        amsat_text = _read_url_text("https://www.amsat.org/tle/current/nasabare.txt", timeout=8)
        amsat_items = _parse_tle_triplets(amsat_text)

        # 3) ISS update from ARISS
        iss_text = _read_url_text("https://live.ariss.org/iss.txt", timeout=8)
        iss_items = _parse_tle_triplets(iss_text)

        # Remove old ISS-like entries then inject latest ISS from ARISS
        merged = [s for s in existing if "ISS" not in (s.get("name", "").upper()) and "ZARYA" not in (s.get("name", "").upper())]
        merged.extend(iss_items)

        # 2) Add new AMSAT lines (dedupe by exact 3-line block)
        merged_keys = set((s.get("name", "").strip().upper(), s.get("line1", "").strip(), s.get("line2", "").strip()) for s in merged)
        for s in amsat_items:
            k = (s.get("name", "").strip().upper(), s.get("line1", "").strip(), s.get("line2", "").strip())
            if k not in merged_keys:
                merged.append(s)
                merged_keys.add(k)

        # Persist merged catalog in 3-line TLE format
        if merged:
            lines_out = []
            for s in merged:
                n = (s.get("name") or "Unknown").strip()
                l1 = (s.get("line1") or "").strip()
                l2 = (s.get("line2") or "").strip()
                if l1.startswith("1 ") and l2.startswith("2 "):
                    lines_out.extend([n, l1, l2])
            if lines_out:
                with open(TLE_ACTIVE_PATH, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines_out) + "\n")

        # Update in-memory cache/status (mutation in-place — preserves identity)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cache_items = []
        for s in merged[:1000]:
            cache_items.append({
                "name": s.get("name") or "Unknown",
                "norad_cat_id": None,
                "tle_line1": s.get("line1") or "",
                "tle_line2": s.get("line2") or "",
                "object_type": None,
                "epoch": None,
            })
        TLE_CACHE.update({
            "status": "connected",
            "source": "AMSAT nasabare + ARISS ISS",
            "last_refresh_iso": now_iso,
            "count": len(cache_items),
            "items": cache_items,
            "error": None,
        })
        HEALTH_STATE["mode"] = "LIVE"
        HEALTH_STATE["tle_status"] = "connected"

        try:
            HEALTH_STATE["tle_last_refresh"] = now_iso
            HEALTH_STATE["tle_source"] = TLE_CACHE.get("source")
        except Exception:
            pass

        log.info("refresh_tle_from_amsat: merged=%s amsat=%s iss=%s", len(merged), len(amsat_items), len(iss_items))
        if os.path.isfile(TLE_ACTIVE_PATH):
            log.info("TLE FILE SIZE: %s", os.path.getsize(TLE_ACTIVE_PATH))
        return True
    except Exception as e:
        log.warning("refresh_tle_from_amsat: %s", e)
        return False


def _download_tle_catalog():
    """Télécharge le catalogue TLE actif depuis Celestrak vers data/tle/active.tle."""
    from app.services.tle_cache import TLE_ACTIVE_PATH
    from station_web import log

    try:
        url = "https://live.ariss.org/iss.txt"
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            text = r.read().decode("utf-8", errors="replace")
        if text and len(text) > 1000:
            with open(TLE_ACTIVE_PATH, "w", encoding="utf-8") as f:
                f.write(text)
            log.info("TLE catalog downloaded to %s", TLE_ACTIVE_PATH)
        else:
            raise RuntimeError("TLE content too small")
    except Exception as e:
        log.warning("download_tle_catalog: %s", e)


def _run_tle_download_once():
    """Exécute un cycle complet refresh_tle_from_amsat puis re-schedule à +6h."""
    try:
        refresh_tle_from_amsat()
    except Exception:
        try:
            print("TLE skipped — offline mode")
        except Exception:
            pass
    t = threading.Timer(6 * 3600.0, _run_tle_download_once)
    t.daemon = True
    t.start()


def _start_tle_collector():
    """Démarre le thread daemon : sleep 60s puis bascule sur _run_tle_download_once."""
    def _run():
        time.sleep(60)
        _run_tle_download_once()
    t = threading.Thread(target=_run, daemon=True)
    t.start()


__all__ = [
    "download_tle_now",
    "refresh_tle_from_amsat",
    "_download_tle_catalog",
    "_run_tle_download_once",
    "_start_tle_collector",
]
