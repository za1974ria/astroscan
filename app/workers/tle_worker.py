"""PASS 27.2 (2026-05-08) — TLE refresh worker (daemon thread).

Extrait depuis station_web.py:476-1186 lors de PASS 27.2.

Ce module regroupe les 4 fonctions liées au refresh TLE périodique :

- ``fetch_tle_from_celestrak()`` — refresh principal depuis SatNOGS (ex
  Celestrak), avec fallbacks en cascade : data_core fresh (<6h) → HTTP →
  data_core stale → ``data/tle/active.tle`` historique → bootstrap local
  layers. Backoff exponentiel + cooldown aléatoire 60-120 s à partir
  du 3e échec consécutif (immune aux ajustements d'horloge via mono).
- ``_tle_next_sleep_seconds()`` — calcule la durée de sommeil du thread,
  respecte la fenêtre de backoff pour réessayer dès la deadline.
- ``load_tle_cache_from_disk()`` — hydrate ``TLE_CACHE`` au boot depuis
  data_core ou le fichier disque ``TLE_CACHE_FILE`` (cycle-safe).
- ``tle_refresh_loop()`` — boucle thread daemon qui appelle
  ``fetch_tle_from_celestrak()`` puis sleep ``_tle_next_sleep_seconds()``.
  Démarrée par ``app/bootstrap.py:35-37`` via le shim
  ``from station_web import tle_refresh_loop``.

Architecture rappelée :
- ``TLE_CACHE`` est un dict identity-stable (cf. ``app/services/tle_cache.py``).
  Toute mutation passe par ``.clear() + .update()`` ou ``.update(...)``
  pour préserver l'identité.
- Backoff/cooldown utilise ``time.monotonic()`` pour être immune aux
  ajustements d'horloge système.
- Lazy imports inside les fonctions pour éviter le cycle station_web ↔
  tle_worker au load (HEALTH_STATE et _orbital_log sont définis dans
  station_web et accédés post-bootstrap).
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timezone

import requests

from app.services.tle_cache import TLE_CACHE, TLE_CACHE_FILE
from app.services.station_state import STATION
from app.services.logging_service import struct_log, _health_set_error
from services.utils import safe_ensure_dir
from services.orbital_service import normalize_celestrak_record
from services.circuit_breaker import CB_TLE

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# TLE CONNECTÉ — SOURCE SatNOGS (Space-Track.org mirror)
# CelesTrak bloqué depuis Hetzner — remplacé par SatNOGS
# ══════════════════════════════════════════════════════════════

TLE_SOURCE_URL = "https://db.satnogs.org/api/tle/?format=json&satellite__status=alive"
TLE_LOCAL_FALLBACK = "/root/astro_scan/data/tle/active.tle"
TLE_REFRESH_SECONDS = 900  # legacy constant (15 minutes)
TLE_DEFAULT_REFRESH_SECONDS = 900
TLE_BACKOFF_REFRESH_SECONDS = 6 * 3600  # legacy (non utilisé : backoff mono + _tle_next_sleep_seconds)
CURRENT_TLE_REFRESH_SECONDS = TLE_DEFAULT_REFRESH_SECONDS
TLE_CONSECUTIVE_FAILURES = 0
TLE_LAST_TIMEOUT_LOG_TS = 0
# Backoff mono pour les fetch TLE : pas de time.time() (immune aux ajustements d'horloge).
TLE_BACKOFF_UNTIL_MONO = 0.0
TLE_BACKOFF_ACTIVE_LOG_MONO = 0.0
TLE_BACKOFF_BASE_SEC = 30
TLE_BACKOFF_EXP_CAP_SEC = 120
TLE_COOLDOWN_AFTER_FAILURES = 3
TLE_COOLDOWN_MIN_SEC = 60
TLE_COOLDOWN_MAX_SEC = 120


def fetch_tle_from_celestrak():
    """Rafraîchit le cache TLE depuis CelesTrak (GP active JSON)."""
    global TLE_CONSECUTIVE_FAILURES, CURRENT_TLE_REFRESH_SECONDS, TLE_LAST_TIMEOUT_LOG_TS
    global TLE_BACKOFF_UNTIL_MONO, TLE_BACKOFF_ACTIVE_LOG_MONO

    # Lazy imports cycle-safe (HEALTH_STATE / _orbital_log définis dans station_web)
    try:
        from station_web import HEALTH_STATE, _orbital_log
    except Exception:
        HEALTH_STATE = {}
        _orbital_log = log

    # Fenêtre de backoff : on ne lance pas HTTP tant que la deadline mono n'est pas passée
    # (le cache disque / local reste servi tel quel — pas d'incrément d'échec sur ce return).
    now_m = time.monotonic()
    if now_m < TLE_BACKOFF_UNTIL_MONO:
        if now_m - TLE_BACKOFF_ACTIVE_LOG_MONO >= 60.0:
            TLE_BACKOFF_ACTIVE_LOG_MONO = now_m
            struct_log(
                logging.INFO,
                category="tle",
                event="fetch_backoff_active",
                remaining_sec=round(TLE_BACKOFF_UNTIL_MONO - now_m, 2),
                consecutive_failures=TLE_CONSECUTIVE_FAILURES,
            )
        return False

    # data_core frais (< 6 h) : pas d'appel réseau — même sémantique de succès que refresh OK
    try:
        from core import tle_engine_safe as _tle_es

        _skip_b = _tle_es.fresh_bundle_for_skip_network(STATION, max_age_seconds=6 * 3600)
        if _skip_b and _skip_b.get("items"):
            _tle_es.merge_bundle_into_tle_cache_dict(TLE_CACHE, _skip_b, preserve_error=None)
            TLE_CACHE["error"] = None
            _orbital_log.info("TLE loaded from cache")
            try:
                if HEALTH_STATE.get("mode") != "LIVE":
                    HEALTH_STATE["mode"] = HEALTH_STATE.get("mode") or "OFFLINE_DATA"
                HEALTH_STATE["tle_status"] = TLE_CACHE.get("status")
                HEALTH_STATE["tle_source"] = TLE_CACHE.get("source")
            except Exception:
                pass
            recovering = TLE_CONSECUTIVE_FAILURES > 0
            TLE_CONSECUTIVE_FAILURES = 0
            TLE_BACKOFF_UNTIL_MONO = 0.0
            TLE_BACKOFF_ACTIVE_LOG_MONO = 0.0
            CURRENT_TLE_REFRESH_SECONDS = TLE_DEFAULT_REFRESH_SECONDS
            if recovering:
                struct_log(
                    logging.INFO,
                    category="tle",
                    event="fetch_recovered",
                    source="data_core_fresh",
                    count=len(TLE_CACHE.get("items") or []),
                )
            return True
    except Exception:
        pass

    try:
        def _fetch_tle_http():
            resp = requests.get(TLE_SOURCE_URL, timeout=5)
            resp.raise_for_status()
            return resp.json()
        data = CB_TLE.call(_fetch_tle_http, fallback=None)
        if data is None:
            struct_log(logging.WARNING, category="tle", event="fetch_circuit_open")
            return False
        if not isinstance(data, list):
            # certains formats renvoient {"member": [...]} — tolérance simple
            data = data.get("member") if isinstance(data, dict) else []
        items = []
        for rec in data:
            norm = normalize_celestrak_record(rec or {})
            if norm:
                items.append(norm)
        # limiter la charge côté backend/front (Cesium)
        if len(items) > 1000:
            items = items[:1000]
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # PASS 23.5 — mutation in-place pour préserver l'identité du dict
        # (le re-export shim app.services.tle_cache repose sur cette invariant).
        TLE_CACHE.clear()
        TLE_CACHE.update({
            "status": "connected",
            "source": "CelesTrak GP active JSON",
            "last_refresh_iso": ts,
            "count": len(items),
            "items": items,
            "error": None,
        })
        try:
            safe_ensure_dir(TLE_CACHE_FILE)
            with open(TLE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(TLE_CACHE, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"[TLE] cache file write failed: {e}")
        try:
            from core import tle_engine_safe as _tle_es

            _tle_es.save_tle_local(STATION, TLE_CACHE)
        except Exception:
            pass
        _orbital_log.info("TLE refreshed from remote")
        _orbital_log.info(f"[TLE] connected refresh OK count={len(items)} source=CelesTrak")
        struct_log(
            logging.INFO,
            category="tle",
            event="fetch_ok",
            source="celestrak_json",
            count=len(items),
        )
        # Succès réseau : réinitialise compteur + backoff ; log recovery si on sort d'une série d'échecs.
        recovering = TLE_CONSECUTIVE_FAILURES > 0
        TLE_CONSECUTIVE_FAILURES = 0
        TLE_BACKOFF_UNTIL_MONO = 0.0
        TLE_BACKOFF_ACTIVE_LOG_MONO = 0.0
        CURRENT_TLE_REFRESH_SECONDS = TLE_DEFAULT_REFRESH_SECONDS
        if recovering:
            struct_log(
                logging.INFO,
                category="tle",
                event="fetch_recovered",
                source="celestrak_json",
                count=len(items),
            )
        return True
    except Exception as e:
        msg = str(e)
        lower_msg = msg.lower()
        is_timeout = (
            isinstance(e, requests.exceptions.Timeout)
            or "timed out" in lower_msg
            or "connecttimeout" in lower_msg
            or "read timeout" in lower_msg
        )
        # Timeout fallback: priorité data_core/tle puis active.tle historique (3 lignes).
        if is_timeout:
            try:
                from core import tle_engine_safe as _tle_es

                dc = _tle_es.load_local_tle(STATION)
                if dc and dc.get("items"):
                    _tle_es.merge_bundle_into_tle_cache_dict(TLE_CACHE, dc, preserve_error=msg)
                    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    TLE_CACHE["status"] = "cached"
                    TLE_CACHE["last_refresh_iso"] = TLE_CACHE.get("last_refresh_iso") or ts
                    try:
                        if HEALTH_STATE.get("mode") != "LIVE":
                            HEALTH_STATE["mode"] = HEALTH_STATE.get("mode") or "OFFLINE_DATA"
                        HEALTH_STATE["tle_status"] = "cached"
                        HEALTH_STATE["tle_source"] = TLE_CACHE.get("source")
                    except Exception:
                        pass
                    recovering = TLE_CONSECUTIVE_FAILURES > 0
                    TLE_CONSECUTIVE_FAILURES = 0
                    TLE_BACKOFF_UNTIL_MONO = 0.0
                    TLE_BACKOFF_ACTIVE_LOG_MONO = 0.0
                    CURRENT_TLE_REFRESH_SECONDS = TLE_DEFAULT_REFRESH_SECONDS
                    _orbital_log.info("TLE fallback used")
                    struct_log(
                        logging.WARNING,
                        category="tle",
                        event="fetch_fallback_data_core",
                        count=len(TLE_CACHE.get("items") or []),
                        detail=msg[:300],
                    )
                    if recovering:
                        struct_log(
                            logging.INFO,
                            category="tle",
                            event="fetch_recovered",
                            source="data_core_stale",
                            count=len(TLE_CACHE.get("items") or []),
                        )
                    return True
            except Exception:
                pass
            try:
                local_tle_path = f"{STATION}/data/tle/active.tle"
                if os.path.isfile(local_tle_path) and os.path.getsize(local_tle_path) > 0:
                    with open(local_tle_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_lines = [ln.strip() for ln in f.readlines() if ln and ln.strip()]

                    parsed_items = []
                    i = 0
                    while i + 2 < len(raw_lines):
                        name = raw_lines[i].strip()
                        l1 = raw_lines[i + 1].strip()
                        l2 = raw_lines[i + 2].strip()
                        if l1.startswith("1 ") and l2.startswith("2 "):
                            parsed_items.append({
                                "name": name,
                                "norad_cat_id": None,
                                "tle_line1": l1,
                                "tle_line2": l2,
                                "object_type": None,
                                "epoch": None,
                            })
                            i += 3
                            continue
                        i += 1

                    # Requirement: never keep count=0 if local file exists and is non-empty.
                    if not parsed_items:
                        prev = (TLE_CACHE.get("items") or []) if isinstance(TLE_CACHE, dict) else []
                        if prev:
                            parsed_items = prev

                    if parsed_items:
                        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        # PASS 23.5 — capture last_refresh_iso AVANT clear()
                        # (sinon get() retourne None après le clear).
                        _prev_last_iso = TLE_CACHE.get("last_refresh_iso") or ts
                        TLE_CACHE.clear()
                        TLE_CACHE.update({
                            "status": "cached",
                            "source": "Local active.tle fallback",
                            "last_refresh_iso": _prev_last_iso,
                            "count": len(parsed_items),
                            "items": parsed_items,
                            "error": msg,
                        })
                        try:
                            # Do not overwrite LIVE mode if AMSAT refresh already succeeded.
                            if HEALTH_STATE.get("mode") != "LIVE":
                                HEALTH_STATE["mode"] = HEALTH_STATE.get("mode") or "OFFLINE_DATA"
                            HEALTH_STATE["tle_status"] = "cached"
                            HEALTH_STATE["tle_source"] = TLE_CACHE.get("source")
                        except Exception:
                            pass
                        # Fallback local OK : même sémantique que succès (données utilisables, on sort du backoff).
                        recovering = TLE_CONSECUTIVE_FAILURES > 0
                        TLE_CONSECUTIVE_FAILURES = 0
                        TLE_BACKOFF_UNTIL_MONO = 0.0
                        TLE_BACKOFF_ACTIVE_LOG_MONO = 0.0
                        CURRENT_TLE_REFRESH_SECONDS = TLE_DEFAULT_REFRESH_SECONDS
                        struct_log(
                            logging.WARNING,
                            category="tle",
                            event="fetch_fallback_local_tle",
                            count=len(parsed_items),
                            detail=msg[:300],
                        )
                        if recovering:
                            struct_log(
                                logging.INFO,
                                category="tle",
                                event="fetch_recovered",
                                source="local_active_tle",
                                count=len(parsed_items),
                            )
                        return True
            except Exception:
                pass

        now_ts = time.time()
        allow_timeout_log = True
        if is_timeout:
            # Log timeout at most once per hour.
            if now_ts - TLE_LAST_TIMEOUT_LOG_TS < 3600:
                allow_timeout_log = False
            else:
                TLE_LAST_TIMEOUT_LOG_TS = now_ts

        if allow_timeout_log:
            _orbital_log.warning(f"[TLE] refresh failed: {msg}")
            try:
                _health_set_error("tle_refresh", msg, "warn")
            except Exception:
                pass

        # Dernier filet : cache vide → toutes couches locales (data_core + legacy)
        try:
            from core import tle_engine_safe as _tle_es

            if not (TLE_CACHE.get("items") or []):
                fb = _tle_es.bootstrap_from_local_layers(STATION)
                if fb and fb.get("items"):
                    _tle_es.merge_bundle_into_tle_cache_dict(TLE_CACHE, fb, preserve_error=msg)
                    try:
                        if HEALTH_STATE.get("mode") != "LIVE":
                            HEALTH_STATE["mode"] = HEALTH_STATE.get("mode") or "OFFLINE_DATA"
                        HEALTH_STATE["tle_status"] = "cached"
                        HEALTH_STATE["tle_source"] = TLE_CACHE.get("source")
                    except Exception:
                        pass
                    recovering = TLE_CONSECUTIVE_FAILURES > 0
                    TLE_CONSECUTIVE_FAILURES = 0
                    TLE_BACKOFF_UNTIL_MONO = 0.0
                    TLE_BACKOFF_ACTIVE_LOG_MONO = 0.0
                    CURRENT_TLE_REFRESH_SECONDS = TLE_DEFAULT_REFRESH_SECONDS
                    _orbital_log.info("TLE fallback used")
                    struct_log(
                        logging.WARNING,
                        category="tle",
                        event="fetch_fallback_bootstrap",
                        count=len(TLE_CACHE.get("items") or []),
                        detail=msg[:300],
                    )
                    if recovering:
                        struct_log(
                            logging.INFO,
                            category="tle",
                            event="fetch_recovered",
                            source="local_bootstrap",
                            count=len(TLE_CACHE.get("items") or []),
                        )
                    return True
        except Exception:
            pass

        # Échec après tentative réseau : backoff exponentiel puis cooldown aléatoire 60–120 s à partir du 3e échec.
        TLE_CONSECUTIVE_FAILURES += 1
        mono = time.monotonic()
        if TLE_CONSECUTIVE_FAILURES >= TLE_COOLDOWN_AFTER_FAILURES:
            cd = random.randint(TLE_COOLDOWN_MIN_SEC, TLE_COOLDOWN_MAX_SEC)
            TLE_BACKOFF_UNTIL_MONO = mono + float(cd)
            struct_log(
                logging.WARNING,
                category="tle",
                event="fetch_backoff_start",
                cooldown_sec=cd,
                consecutive_failures=TLE_CONSECUTIVE_FAILURES,
            )
        else:
            exp_delay = min(
                TLE_BACKOFF_EXP_CAP_SEC,
                int(TLE_BACKOFF_BASE_SEC * (2 ** (TLE_CONSECUTIVE_FAILURES - 1))),
            )
            TLE_BACKOFF_UNTIL_MONO = mono + float(exp_delay)

        # conserver l'ancien cache, seulement marquer l'erreur
        try:
            TLE_CACHE["error"] = msg
        except Exception:
            pass
        struct_log(
            logging.WARNING,
            category="tle",
            event="fetch_failed",
            error=msg[:500],
            consecutive_failures=TLE_CONSECUTIVE_FAILURES,
        )
        return False


def _tle_next_sleep_seconds():
    """
    Sommeil entre deux tentatives TLE : respecte le backoff mono pour réessayer
    dès la fin de la fenêtre sans attendre tout le cycle 900 s.
    """
    try:
        now_m = time.monotonic()
        if now_m < TLE_BACKOFF_UNTIL_MONO:
            left = TLE_BACKOFF_UNTIL_MONO - now_m
            return max(1.0, min(float(left), float(CURRENT_TLE_REFRESH_SECONDS)))
        return float(CURRENT_TLE_REFRESH_SECONDS)
    except Exception:
        return float(CURRENT_TLE_REFRESH_SECONDS)


def load_tle_cache_from_disk():
    """Charge un cache TLE existant depuis le disque, si possible."""
    # Lazy import cycle-safe (_orbital_log défini dans station_web)
    try:
        from station_web import _orbital_log
    except Exception:
        _orbital_log = log

    # Couche additive : data_core/tle puis caches legacy (sans retirer le flux historique)
    try:
        from core import tle_engine_safe as _tle_es

        boot = _tle_es.bootstrap_from_local_layers(STATION)
        if boot and isinstance(boot.get("items"), list) and len(boot["items"]) > 0:
            TLE_CACHE.update(
                status=boot.get("status") or "cached",
                source=boot.get("source") or "CelesTrak GP active JSON (cache)",
                last_refresh_iso=boot.get("last_refresh_iso"),
                count=len(boot["items"]),
                items=boot["items"],
                error=boot.get("error"),
            )
            _orbital_log.info("TLE loaded from cache")
    except Exception:
        pass
    try:
        if TLE_CACHE.get("items"):
            return True
        if not os.path.exists(TLE_CACHE_FILE):
            return False
        with open(TLE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        # hydratation minimale — on ne fait pas confiance aveuglément au fichier
        items = data.get("items") or []
        if not isinstance(items, list):
            items = []
        TLE_CACHE.update(
            status=data.get("status") or "cached",
            source=data.get("source") or "CelesTrak GP active JSON (cache)",
            last_refresh_iso=data.get("last_refresh_iso"),
            count=len(items),
            items=items,
            error=data.get("error"),
        )
        if items:
            _orbital_log.info(f"[TLE] disk cache loaded count={len(items)}")
        return True
    except Exception as e:
        _orbital_log.warning(f"[TLE] load cache failed: {e}")
        return False


def tle_refresh_loop():
    """Boucle de rafraîchissement périodique TLE (thread daemon)."""
    # Lazy import cycle-safe (_orbital_log défini dans station_web)
    try:
        from station_web import _orbital_log
    except Exception:
        _orbital_log = log

    while True:
        try:
            fetch_tle_from_celestrak()
        except Exception as e:
            _orbital_log.warning(f"[TLE] background refresh error: {e}")
        try:
            time.sleep(_tle_next_sleep_seconds())
        except Exception:
            # si sleep échoue, on retente rapidement pour éviter un spin infini
            time.sleep(5)
