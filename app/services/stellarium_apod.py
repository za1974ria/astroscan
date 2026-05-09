"""PASS 27.3 (2026-05-09) — Stellarium + NASA APOD enrichment helpers.

Extrait depuis station_web.py:523-768 lors de PASS 27.3.

Ce module regroupe les 5 fonctions helper qui alimentent l'enrichissement
Stellarium + NASA APOD de ``_build_status_payload_dict()`` (et son fallback
``_fallback_status_payload_dict()``), exposés au blueprint ``health``
(``/api/health``, ``/health``).

- ``load_stellarium_data()`` — lit les exports JSON dans
  ``<STATION>/data/stellarium/`` (création silencieuse du dossier si absent,
  fichiers invalides ignorés sans planter l'app).
- ``compute_stellarium_freshness(last_timestamp)`` — qualifie un timestamp
  ISO en ``live`` (<60 s), ``recent`` (<300 s), ``stale`` (>=300 s),
  ``unknown`` sinon. Aware/naive coerce en UTC.
- ``build_priority_object(stellarium_data, freshness)`` — construit un
  « objet prioritaire » fusion (score 0-100, confidence 0-100) à partir
  du dernier enregistrement Stellarium + score de fraîcheur.
- ``build_system_intelligence(...)`` — couche fusion v1 : agrège les
  signaux (TLE freshness, mode prod, Stellarium, priority object) en
  ``fusion_score`` + ``risk_level`` + ``global_status``.
- ``get_nasa_apod()`` — récupère l'APOD NASA (Astronomy Picture of the
  Day) avec cache 30 minutes pour éviter de spammer l'API à chaque
  requête /status. Timeout 5 s, fallback dict vide en cas d'échec réseau.

Architecture rappelée :
- Imports directs depuis les modules source (``app.services.station_state``,
  ``app.services.logging_service``, ``services.cache_service``,
  ``services.utils``) — aucun chemin ne repasse par ``station_web``,
  donc pas de cycle, pas besoin de lazy imports.
- Les 5 fonctions sont ré-exportées depuis ``station_web.py`` pour
  préserver les appels internes de ``_build_status_payload_dict``
  (ligne ~2200) et ``_fallback_status_payload_dict`` (ligne ~2136).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import requests

from app.services.station_state import STATION
from app.services.logging_service import struct_log
from services.cache_service import cache_get, cache_set
from services.utils import safe_ensure_dir

log = logging.getLogger(__name__)


def load_stellarium_data():
    """
    Charge les fichiers *.json du dossier data/stellarium (exports / observations Stellarium).
    Crée le dossier si absent ; ignore les fichiers invalides sans faire tomber l'app.
    """
    folder = os.path.join(STATION, "data", "stellarium")
    data = []
    try:
        safe_ensure_dir(folder)
    except Exception:
        pass
    if not os.path.isdir(folder):
        return data
    try:
        for name in sorted(os.listdir(folder)):
            if not str(name).lower().endswith(".json"):
                continue
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as fp:
                    payload = json.load(fp)
                if payload is not None:
                    data.append(payload)
            except Exception as ex:
                log.warning("[Stellarium] Failed to load %s: %s", name, ex)
    except Exception as ex:
        log.warning("[Stellarium] folder read failed: %s", ex)
    return data


def compute_stellarium_freshness(last_timestamp):
    """Indicateur temporel sûr à partir du timestamp Stellarium (ISO ou assimilé)."""
    freshness = "unknown"
    if not last_timestamp:
        return freshness
    try:
        ts_raw = last_timestamp if isinstance(last_timestamp, str) else str(last_timestamp)
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - ts).total_seconds()
        if delta < 60:
            freshness = "live"
        elif delta < 300:
            freshness = "recent"
        else:
            freshness = "stale"
    except Exception:
        freshness = "unknown"
    return freshness


def build_priority_object(stellarium_data, freshness):
    """Objet prioritaire « fusion » à partir du dernier enregistrement Stellarium (mode sûr)."""
    try:
        if not stellarium_data:
            return None
        tail = stellarium_data[-1]
        last = tail if isinstance(tail, dict) else {}

        name = last.get("object")
        obj_type = last.get("type", "unknown")
        visibility = last.get("visibility", "unknown")

        score = 0
        reason = []

        if freshness == "live":
            score += 40
            reason.append("live data")
        elif freshness == "recent":
            score += 25
            reason.append("recent data")
        elif freshness == "stale":
            score += 5
            reason.append("stale data")

        if visibility == "visible":
            score += 30
            reason.append("visible")

        if obj_type == "satellite":
            score += 30
            reason.append("satellite")
        elif obj_type == "planet":
            score += 20
            reason.append("planet")
        elif obj_type == "star":
            score += 10
            reason.append("star")

        score = min(score, 100)

        confidence = 0
        if freshness == "live":
            confidence += 50
        elif freshness == "recent":
            confidence += 30
        else:
            confidence += 10
        if visibility == "visible":
            confidence += 30
        confidence = min(confidence, 100)

        return {
            "name": name,
            "source": "stellarium",
            "type": obj_type,
            "score": score,
            "confidence": confidence,
            "reason": " + ".join(reason),
        }
    except Exception:
        return None


def build_system_intelligence(
    system_status,
    production_mode,
    tle_data_freshness,
    observation_mode,
    stellarium_freshness,
    stellarium_active,
    priority_object,
):
    """
    Couche fusion légère : résume les signaux déjà calculés (TLE, Stellarium, priorité).
    Tout en .get / try — prêt pour extension multi-sources (NASA, etc.).
    """
    try:
        po = priority_object if isinstance(priority_object, dict) else None

        def _safe_int(v):
            try:
                if v is None:
                    return None
                return int(v)
            except (TypeError, ValueError):
                return None

        p_score = _safe_int(po.get("score")) if po else None
        p_conf = _safe_int(po.get("confidence")) if po else None

        fusion = 0
        if p_score is not None:
            fusion += min(50, max(0, p_score) // 2)
        if p_conf is not None:
            fusion += min(50, max(0, p_conf) // 2)
        fusion = min(100, fusion)

        if fusion >= 75:
            risk_level = "HIGH"
        elif fusion >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        pm = str(production_mode or "").strip().upper()
        df = str(tle_data_freshness or "").strip().lower()
        if pm == "LIVE" and df == "fresh":
            global_status = "OPERATIONAL"
        elif pm == "DEMO":
            global_status = "SIMULATION"
        else:
            global_status = "DEGRADED"

        return {
            "layer": "fusion_v1",
            "inputs": {
                "system_status": system_status,
                "production_mode": production_mode,
                "tle_data_freshness": tle_data_freshness,
                "observation_mode": observation_mode,
                "stellarium": {
                    "freshness": stellarium_freshness or "unknown",
                    "active": bool(stellarium_active),
                },
            },
            "priority_score": p_score,
            "priority_confidence": p_conf,
            "fusion_score": fusion,
            "risk_level": risk_level,
            "global_status": global_status,
        }
    except Exception:
        return {
            "layer": "fusion_v1",
            "inputs": {},
            "priority_score": None,
            "priority_confidence": None,
            "fusion_score": 0,
            "risk_level": "LOW",
            "global_status": "DEGRADED",
        }


def get_nasa_apod():
    """APOD NASA pour enrichissement visuel /status (échec réseau → dict vide, timeout ≤ 5 s).
    Cache 30 minutes pour éviter de spammer l'API à chaque appel de /status."""
    _APOD_CACHE_KEY = "get_nasa_apod_v1"
    _APOD_CACHE_TTL = 1800  # 30 minutes
    cached = cache_get(_APOD_CACHE_KEY, _APOD_CACHE_TTL)
    if cached is not None:
        return cached
    try:
        key = (os.environ.get("NASA_API_KEY") or "DEMO_KEY").strip()
        url = f"https://api.nasa.gov/planetary/apod?api_key={key}"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            struct_log(
                logging.WARNING,
                category="nasa",
                event="apod_api_failure",
                status_code=r.status_code,
            )
            cache_set(_APOD_CACHE_KEY, {})
            return {}
        data = r.json()
        if not isinstance(data, dict):
            struct_log(
                logging.WARNING,
                category="nasa",
                event="apod_parse_failure",
                detail="non_object_json",
            )
            cache_set(_APOD_CACHE_KEY, {})
            return {}
        if not data.get("url") and not data.get("hdurl"):
            struct_log(
                logging.INFO,
                category="nasa",
                event="apod_empty_visual",
            )
        cache_set(_APOD_CACHE_KEY, data)
        return data
    except Exception as ex:
        struct_log(
            logging.WARNING,
            category="nasa",
            event="apod_request_failed",
            error=str(ex)[:300],
        )
    cache_set(_APOD_CACHE_KEY, {})
    return {}
