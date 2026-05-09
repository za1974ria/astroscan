# ╔══════════════════════════════════════════════════════════════════╗
# ║  FICHIER EN COURS DE MIGRATION — NE PAS AJOUTER DE NOUVELLES    ║
# ║  ROUTES ICI. Utiliser app/blueprints/ à la place.               ║
# ║  Voir MIGRATION_PLAN.md + ARCHITECTURE.md                        ║
# ╚══════════════════════════════════════════════════════════════════╝
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║  ORBITAL-CHOHRA — station_web.py — VERSION COMPLÈTE          ║
║  Directeur : Zakaria Chohra · Tlemcen · 5.78.153.17        ║
║  Reconstruit intégralement                                   ║
╚══════════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────────────────────

import os
import sys

if __name__ == "__main__":
    print("❌ Lancement manuel interdit. Utilisez systemctl.")
    sys.exit(1)

# PASS 19 cleanup : os/sys déjà importés au-dessus, doublons retirés.
import json
import sqlite3
import re
import time
import random
import logging
import subprocess
import threading
import requests
import secrets
import fcntl
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone, timedelta

# PASS 26.A — Sentry init removed from monolith.
# Centralized in app/__init__.py:_init_sentry (called by create_app).
# Avoids double-init that replaces the global hub.
from flask import Flask, render_template, jsonify, request, g
# PASS 19 cleanup : flask {redirect, send_file, abort, make_response,
# stream_with_context, Response} et werkzeug.secure_filename retirés (utilisés
# uniquement dans des routes/handlers déjà migrés vers les BPs).
# PASS 25.2 residue : send_from_directory retiré — /static est servi par
# Flask via static_folder du factory (app/__init__.py).
from app.services.orbit_sgp4 import propagate_tle_debug  # noqa: F401 — re-export pour BPs
from app.services.satellites import SATELLITES, list_satellites, get_satellite_tle_name_map  # noqa: F401 — re-export pour BPs
from app.services.accuracy_history import get_accuracy_history, get_accuracy_stats  # noqa: F401 — re-export pour BPs
# PASS 2D Cat 1 (2026-05-07) : extraction visitors → app/services/db_visitors.py
from app.services.db_visitors import (  # noqa: F401 — re-export pour BPs (compat legacy)
    _get_visits_count,
    _increment_visits,
    _compute_human_score,
    _invalidate_owner_ips_cache,
    _load_owner_ips,
    _is_owner_ip,
    _register_unique_visit_from_request,
)
# PASS 2D Cat 2 (2026-05-07) : extraction TLE → app/services/tle.py
from app.services.tle import (  # noqa: F401 — re-export pour BPs + station_web internals
    TLE_ACTIVE_PATH,
    _parse_tle_file,
    _TLE_FOR_PASSES,
)
# PASS 2D Cat 5 (2026-05-07) : extraction security → app/services/security.py
from app.services.security import (  # noqa: F401 — re-export pour BPs (compat legacy)
    _api_rate_limit_allow,
    _client_ip_from_request,
)
# api_iss_impl : iss_bp l'importe directement depuis app.routes.iss (PASS 16),
# plus besoin du re-export ici.
# MIGRATED TO sdr_bp 2026-05-02 — see app/blueprints/sdr/routes.py
# from app.routes.sdr import api_sdr_passes_impl
# MIGRATED TO apod_bp 2026-05-02 — see app/blueprints/apod/routes.py
# from app.routes.apod import apod_fr_json_impl, apod_fr_view_impl
from services.stats_service import get_global_stats  # noqa: F401 — re-export pour analytics_bp
from services.weather_service import (
    compute_weather_score, generate_weather_bulletin, compute_reliability,
)
# PASS 19 cleanup : weather_service.{interpretWeatherCode, normalize_weather,
# compute_weather_reliability, validate_data, compute_risk, _internal_weather_fallback,
# _derive_weather_condition, _safe_kp_value, _kp_premium_profile,
# _build_local_weather_payload, get_weather_snapshot, get_kp_index,
# get_aurora_data, get_space_weather} retirés (utilisés par weather_bp directement).
# nasa_service.* retirés (feeds_bp + ai_bp importent en direct).
from services.orbital_service import (
    compute_tle_risk_signal, build_final_core, normalize_celestrak_record,
)
# PASS 19 cleanup : orbital_service.{get_iss_position, get_iss_orbit, load_tle_data,
# compute_satellite_track} retirés (BPs importent en direct).
from services.cache_service import cache_get, cache_set, get_cached
# PASS 19 cleanup : cache_service.{ANALYTICS_CACHE, cache_cleanup, invalidate_cache,
# invalidate_all, cache_status} retirés (BPs importent via app.utils.cache).
# ephemeris_service.* retirés (astro_bp importe en direct).
from services.utils import (
    _is_bot_user_agent, _parse_iso_to_epoch_seconds,
    _safe_json_loads, safe_ensure_dir,
)
# PASS 19 cleanup : services.utils._detect_lang retiré (utilisé uniquement
# par _gemini_translate, supprimé en PASS 19).
from services.db import init_all_wal
# PASS 19 cleanup : services.db.get_db (alias get_db_ctx) retiré (BPs utilisent
# app.utils.db directement).
from services.circuit_breaker import CB_TLE
# PASS 19 cleanup : circuit_breaker.{CB_NASA, CB_N2YO, CB_NOAA, CB_ISS, CB_METEO,
# CB_GROQ, all_status} retirés (BPs/services importent en direct ; le _call_groq
# monolithe a été supprimé en PASS 19, donc CB_GROQ devient orphelin).
# services.config as _cfg retiré (non utilisé).

# ── Instrumentation légère des appels externes requests (timeout + logs JSON) ──
# PASS 22.2 (2026-05-08) — _REQ_* timeouts déplacés vers app/services/db_init.py
# Re-importés via le shim consolidé après l'import de STATION (plus bas).
_REQ_ORIGINAL_REQUEST = requests.sessions.Session.request


def _emit_diag_json(payload):
    """Émet un JSON diagnostique en stdout + logger."""
    try:
        msg = json.dumps(payload, ensure_ascii=False)
    except Exception:
        msg = json.dumps({"event": "diag_encode_failed"}, ensure_ascii=False)
    try:
        print(msg, flush=True)
    except Exception:
        pass
    try:
        log.info(msg)
    except Exception:
        pass


def _requests_instrumented_request(self, method, url, **kwargs):
    if kwargs.get("timeout", None) is None:
        kwargs["timeout"] = _REQ_DEFAULT_TIMEOUT
    t0 = time.time()
    try:
        resp = _REQ_ORIGINAL_REQUEST(self, method, url, **kwargs)
        dur_ms = round((time.time() - t0) * 1000, 2)
        if dur_ms >= _REQ_SLOW_MS:
            _emit_diag_json(
                {
                    "event": "external_call_timing",
                    "url": str(url),
                    "method": str(method).upper(),
                    "status": getattr(resp, "status_code", None),
                    "duration_ms": dur_ms,
                }
            )
        return resp
    except Exception as e:
        _emit_diag_json(
            {
                "event": "external_call_failed",
                "url": str(url),
                "method": str(method).upper(),
                "error": str(e),
            }
        )
        raise


requests.sessions.Session.request = _requests_instrumented_request

# In-memory translation cache / throttling guardrails
TRANSLATE_CACHE = {}
TRANSLATE_TTL_SECONDS = 3600
TRANSLATE_LAST_REQUEST_TS = 0.0

TRANSLATION_CACHE = {}
# PASS 22.2 — MAX_CACHE_SIZE déplacé vers app/services/db_init.py (shim plus bas).


# PASS 20.4 (2026-05-08) — System/Accuracy helpers extracted to app/services/system_helpers.py
# Shim re-exports for backward compatibility (api_bp, health_bp, export_bp utilisent
# `from station_web import STATION, START_TIME, get_accuracy_history, get_accuracy_stats`
# via lazy imports.)
# Note : `server_ready` (bool mutable top-level réassigné False→True après boot)
# n'est PAS migré — la sémantique de réassignation ne survivrait pas à
# l'extraction sans changer l'API. Conservé in-place ci-dessous.
from app.services.system_helpers import (  # noqa: E402,F401
    STATION,
    START_TIME,
    get_accuracy_history,
    get_accuracy_stats,
)
# Passe à True en fin de chargement du module (après routes + init TLE) — utilisé par GET /ready.
server_ready = False

CLAUDE_CALL_COUNT = 0
# PASS 22.2 — CLAUDE_MAX_CALLS déplacé vers app/services/db_init.py (shim plus bas).
CLAUDE_80_WARNING_SENT = False
GROQ_CALL_COUNT = 0
COLLECTOR_LAST_RUN = 0

# ── Config ──────────────────────────────────────────────────
# PASS 23 — moved to app/services/station_state.py
from app.services.station_state import STATION  # noqa: F401 (re-export)
# PASS 22.2 (2026-05-08) — DB inits + config constants extracted to app/services/db_init.py
# Shim re-exports for backward compatibility.
# NOTE: STATION, START_TIME, CLAUDE_CALL_COUNT, GROQ_CALL_COUNT, TRANSLATE_CACHE
# et autres globals mutables restent dans station_web (sémantique de mutation
# top-level préservée dans le namespace monolith).
from app.services.db_init import (  # noqa: E402,F401
    _REQ_DEFAULT_TIMEOUT,
    _REQ_SLOW_MS,
    _REQ_VERY_SLOW_MS,
    MAX_CACHE_SIZE,
    CLAUDE_MAX_CALLS,
    DB_PATH,
    IMG_PATH,
    _init_sqlite_wal,
    _init_visits_table,
    _init_session_tracking_db,
)
# FIXED 2026-05-02 — chemin relatif → absolu via STATION (BUG 2)

# PASS 22.1 (2026-05-08) — Weather DB helpers extracted to app/services/weather_db.py
# Shim re-exports for backward compatibility (les usages internes du monolith
# l.454-456 init_weather_db()/_init_weather_history_dir()/_init_weather_archive_dir()
# continuent de fonctionner via la liaison du shim au namespace).
# STATION reste défini dans station_web (ligne 190) — le service weather_db
# l'importe directement depuis app.services.station_state (canonique, no cycle).
from app.services.weather_db import (  # noqa: E402,F401
    WEATHER_DB_PATH,
    WEATHER_HISTORY_DIR,
    WEATHER_ARCHIVE_DIR,
    init_weather_db,
    _init_weather_history_dir,
    _cleanup_weather_history_files,
    _init_weather_archive_dir,
    _cleanup_weather_archive_files,
    save_weather_archive_json,
    save_weather_history_json,
    save_weather_bulletin,
)

# ─── SQLite WAL mode (performance) ──────────────────────────────────────────
# PASS 22.2 — def _init_sqlite_wal déplacée vers app/services/db_init.py
# (ré-importée via le shim plus haut). L'appel synchrone au boot reste ici :
_init_sqlite_wal()
init_all_wal()   # WAL + busy_timeout sur TOUTES les bases via services/db.py
# ─────────────────────────────────────────────────────────────────────────────


# PASS 22.1 (2026-05-08) — Les 8 fonctions weather DB ont été déplacées
# verbatim vers app/services/weather_db.py (ré-importées via le shim plus haut).
# L'init synchrone au boot est conservé : les fonctions sont fournies par le shim
# au moment où elles sont appelées (plus haut dans station_web).
init_weather_db()
_init_weather_history_dir()
_init_weather_archive_dir()
# ─────────────────────────────────────────────────────────────────────────────
# PASS 22.2 — IMG_PATH déplacé vers app/services/db_init.py (shim ci-dessus).
TITLE_F   = f'{STATION}/telescope_live/current_title.txt'
REPORT_F  = f'{STATION}/telescope_live/live_report.txt'
SHIELD_F  = f'{STATION}/data/shield_status.json'
HUB_F     = f'{STATION}/data/telescope_hub.json'
SDR_F     = f'{STATION}/data/sdr_status.json'
PASSAGES_ISS_JSON = f'{STATION}/static/passages_iss.json'
CALC_PASSAGES_SCRIPT = os.path.join(STATION, 'calculateur_passages.py')

# Titre SEO canonique page d'accueil / landing (<title> + og:title, aligné sur le H1 principal)
SEO_HOME_TITLE = 'AstroScan-Chohra'

# Meta description canonique (accueil, og/twitter, intro landing, templates partagés)
SEO_HOME_DESCRIPTION = (
    "AstroScan-Chohra est une plateforme avancée d'analyse et de surveillance spatiale en temps réel. "
    "Suivez les satellites, les missions spatiales et les phénomènes astronomiques."
)

# Charger .env via python-dotenv (et garder la compatibilité avec l'ancien parseur)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(STATION, '.env'))
except Exception:
    pass

env_file = f'{STATION}/.env'
if Path(env_file).exists():
    for line in open(env_file):
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

CESIUM_TOKEN = os.getenv("CESIUM_TOKEN", "")

app = Flask(__name__,
            template_folder=f'{STATION}/templates',
            static_folder=f'{STATION}/static')
app.config['DEBUG'] = False
app.config['TESTING'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True

# PASS 25.3 — legacy register_blueprint() block removed.
# All blueprints are now registered exclusively in app/__init__.py
# via _register_blueprints(app). station_web.app is a dead Flask
# instance kept for backward compatibility (PASS 25.4 will remove it).


# PASS 26.2 (2026-05-08) — @app.context_processor _inject_seo_site_description supprimé.
# Source de vérité : app/hooks.py (registered via app/__init__.py:_register_hooks
# et station_web.py PASS 25.5 fallback safety).


# PASS 2D fix (2026-05-07) — ensure logs directory exists before FileHandler
# Previously os.makedirs was 84 lines later, causing FileNotFoundError on
# fresh deployments (CI, Docker, new servers) — production worked only because
# /root/astro_scan/logs already existed historically.
os.makedirs(f'{STATION}/logs', exist_ok=True)
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [WEB] %(message)s',
    handlers=[
        logging.FileHandler(f'{STATION}/logs/web.log'),
        logging.StreamHandler()
    ])
log = logging.getLogger(__name__)
log.info(
    'AstroScan starting | STATION=%s | production Flask (DEBUG off) | Gunicorn/systemd ready | env loaded',
    STATION,
)
log.info("Claude configured: %s", bool(os.environ.get("ANTHROPIC_API_KEY")))

# ── Error handlers — ADDED 2026-05-02 (BUG 3) ─────────────────────────────
# PASS 26.1 (2026-05-08) — @app.errorhandler(404) _astroscan_404 supprimé.
# Source de vérité : app/hooks.py (registered via app/__init__.py:_register_hooks
# et station_web.py PASS 25.5 fallback safety).


# PASS 26.2 (2026-05-08) — @app.errorhandler(500) _astroscan_500 supprimé.
# Source de vérité : app/hooks.py (registered via app/__init__.py:_register_hooks
# et station_web.py PASS 25.5 fallback safety).
# ────────────────────────────────────────────────────────────────────────────

# ── Noyau additif V2 (répertoires data_core + helpers santé) — échec silencieux si absent
try:
    from core import data_engine as _core_data_engine

    _core_data_engine.ensure_data_core_dirs(STATION)
except Exception:
    _core_data_engine = None
# PASS 23 — moved to app/services/status_engine.py
from app.services.status_engine import _core_status_engine  # noqa: F401 (re-export)


def _run_calculateur_passages_iss():
    """Exécute calculateur_passages.py pour régénérer static/passages_iss.json."""
    try:
        r = subprocess.run(
            [sys.executable, CALC_PASSAGES_SCRIPT],
            cwd=STATION,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            log.error(
                'passages-iss: calculateur échec rc=%s stderr=%s',
                r.returncode,
                (r.stderr or '')[:800],
            )
            return False
        log.info('passages-iss: fichier JSON généré par calculateur_passages.py')
        return os.path.isfile(PASSAGES_ISS_JSON)
    except subprocess.TimeoutExpired:
        log.error('passages-iss: calculateur timeout (>120s)')
        return False
    except Exception as e:
        log.error('passages-iss: calculateur exception %s', e)
        return False


def ensure_passages_iss_json():
    """Si passages_iss.json est absent, lance le calculateur. Retourne True si le fichier existe."""
    if os.path.isfile(PASSAGES_ISS_JSON):
        return True
    log.info('passages-iss: fichier absent, lancement auto du calculateur…')
    return _run_calculateur_passages_iss()


ensure_passages_iss_json()

# Mission-control operational log (rotation 5 MB, 3 backups)
os.makedirs(f'{STATION}/logs', exist_ok=True)
_orbital_handler = RotatingFileHandler(
    f'{STATION}/logs/orbital_system.log',
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8',
)
_orbital_handler.setFormatter(logging.Formatter('%(asctime)s [ORB-CTRL] %(message)s'))
_orbital_log = logging.getLogger('orbital_system')
_orbital_log.setLevel(logging.INFO)
_orbital_log.addHandler(_orbital_handler)
_orbital_log.propagate = False


class _AstroScanJsonLogFormatter(logging.Formatter):
    """Une ligne JSON par enregistrement pour logs/astroscan_structured.log."""

    def format(self, record):
        try:
            ts = (
                datetime.fromtimestamp(record.created, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            merge = getattr(record, "astroscan_extra", None)
            if isinstance(merge, dict):
                doc = {"ts": ts, "level": record.levelname}
                doc.update(merge)
                if "msg" not in doc or doc.get("msg") is None:
                    doc["msg"] = record.getMessage()
                return json.dumps(doc, ensure_ascii=False)
            return json.dumps(
                {
                    "ts": ts,
                    "level": record.levelname,
                    "component": record.name,
                    "msg": record.getMessage(),
                },
                ensure_ascii=False,
            )
        except Exception:
            return json.dumps(
                {
                    "ts": "",
                    "level": "ERROR",
                    "component": "logging",
                    "msg": "json log format failure",
                },
                ensure_ascii=False,
            )


# PASS 23.2 (2026-05-08) — Logging helpers extracted to app/services/logging_service.py
# Shim re-exports for backward compatibility (app/blueprints/health utilise
# _sw.struct_log ; app/services/lab_helpers utilise _health_set_error via lazy import.)
from app.services.logging_service import (  # noqa: E402,F401
    _http_request_log_allow,
    struct_log,
    system_log,
    _health_log_error,
    _health_set_error,
)

# PASS 23.2 (2026-05-08) — Metrics helpers extracted to app/services/metrics_service.py
# Shim re-exports for backward compatibility.
from app.services.metrics_service import (  # noqa: E402,F401
    _metrics_trim_list,
    metrics_record_request,
    metrics_record_struct_error,
    metrics_status_fields,
)

# Init handler structured log (conservé en place car attaché au logger racine au boot) :
_structured_json_handler = RotatingFileHandler(
    f"{STATION}/logs/astroscan_structured.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_structured_json_handler.setFormatter(_AstroScanJsonLogFormatter())
logging.getLogger().addHandler(_structured_json_handler)


# ══════════════════════════════════════════════════════════════
# TLE CONNECTÉ — SOURCE SatNOGS (Space-Track.org mirror)
# CelesTrak bloqué depuis Hetzner — remplacé par SatNOGS
# ══════════════════════════════════════════════════════════════

# PASS 27.2 (2026-05-08) — TLE refresh worker extracted to app/workers/tle_worker.py
# Constants/globals (TLE_SOURCE_URL, TLE_DEFAULT_REFRESH_SECONDS, backoff state, etc.)
# et les 4 fonctions (fetch_tle_from_celestrak, _tle_next_sleep_seconds,
# load_tle_cache_from_disk, tle_refresh_loop) déplacés verbatim. Re-exportés ici
# pour rétrocompatibilité (app/bootstrap.py:22 + system_bp + lecteurs legacy).
from app.workers.tle_worker import (  # noqa: F401 (re-export)
    TLE_SOURCE_URL,
    TLE_LOCAL_FALLBACK,
    TLE_REFRESH_SECONDS,
    TLE_DEFAULT_REFRESH_SECONDS,
    TLE_BACKOFF_REFRESH_SECONDS,
    TLE_BACKOFF_BASE_SEC,
    TLE_BACKOFF_EXP_CAP_SEC,
    TLE_COOLDOWN_AFTER_FAILURES,
    TLE_COOLDOWN_MIN_SEC,
    TLE_COOLDOWN_MAX_SEC,
)
# PASS 23.5 — moved to app/services/tle_cache.py (identity-stable mutable)
# Toutes les mises à jour ailleurs dans ce fichier passent par mutation
# in-place (.clear() + .update()) pour préserver l'identité du dict.
from app.services.tle_cache import TLE_CACHE, TLE_CACHE_FILE  # noqa: F401 (re-export)

# ── Lightweight in-memory health/status (for /status endpoint) ─────────────
HEALTH_STATE = {
    "app_status": "running",
    "mode": "unknown",
    "tle_status": TLE_CACHE.get("status"),
    "tle_last_refresh": TLE_CACHE.get("last_refresh_iso"),
    "tle_source": TLE_CACHE.get("source"),
    "collector_status": {
        "image_collector": "unknown",
        "skyview_sync": "unknown",
    },
    "skyview_status": "unknown",
    "last_sync": None,
    "image_count": None,
    "last_error": None,
    "uptime_seconds": int(time.time() - START_TIME),
    "version": "1.0",
}

STALE_DATA_THRESHOLD_SEC = 86400   # 24 hours
AGING_DATA_THRESHOLD_SEC = 43200  # 12 hours

# PASS 23.2 — _health_log_error + _health_set_error déplacés vers
# app/services/logging_service.py (ré-importés via le shim plus haut).

# PASS 27.3 (2026-05-09) — Stellarium + NASA APOD helpers extracted to
# app/services/stellarium_apod.py (5 fonctions ~238 lignes corps déplacées
# verbatim avec imports directs depuis les modules source — pas de cycle).
# Re-exportées ici pour conserver les appels internes de
# _build_status_payload_dict (ligne ~2200) et _fallback_status_payload_dict
# (ligne ~2136).
from app.services.stellarium_apod import (  # noqa: E402,F401
    load_stellarium_data,
    compute_stellarium_freshness,
    build_priority_object,
    build_system_intelligence,
    get_nasa_apod,
)


# PASS 27.2 (2026-05-08) — TLE refresh worker functions extracted to
# app/workers/tle_worker.py (les 4 fonctions ~480 lignes corps déplacées
# verbatim avec lazy imports inside pour HEALTH_STATE/_orbital_log
# depuis station_web — cycle-safe). Re-exportées ici pour conserver les
# imports legacy `from station_web import fetch_tle_from_celestrak` etc.
# (app/bootstrap.py:22 + app/blueprints/system/__init__.py:30).
from app.workers.tle_worker import (  # noqa: E402,F401
    fetch_tle_from_celestrak,
    _tle_next_sleep_seconds,
    load_tle_cache_from_disk,
    tle_refresh_loop,
)


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# PASS 22.2 — def _init_visits_table + def _init_session_tracking_db déplacées
# vers app/services/db_init.py (ré-importées via le shim en début de fichier).
# Les appels synchrones au boot restent ici pour préserver l'ordre d'init :
_init_session_tracking_db()
_init_visits_table()


# PASS 27.6 (2026-05-09) — HTTP helpers déplacés vers source de vérité unique
# app/services/http_client.py (extrait initialement au PASS 8, commit 901be23,
# mais sans re-export jusqu'ici → doublon supprimé en PASS 27.6).
# Re-exportés ici pour conserver les 12 appels internes du monolithe et
# l'API publique testée par tests/unit/test_pure_services.py.
from app.services.http_client import (  # noqa: F401 (re-export)
    _curl_get,
    _curl_post,
    _curl_post_json,
)


# DUPLICATE REMOVED 2026-05-02 — fusionnée dans la V2 ci-dessous (L.4718~)
# ORIGINAL VERSION 1 KEPT FOR REFERENCE :
# def _translate_to_french(text, max_chars=800):
#     """Pas de traduction automatique pour l'instant."""
#     return text

# ══════════════════════════════════════════════════════════════
# COMPTEUR DE VISITES — uniquement chargements pages HTML
# ══════════════════════════════════════════════════════════════
PAGE_PATHS = {
    '/', '/landing', '/portail', '/dashboard', '/overlord_live', '/galerie', '/observatoire',
    '/vision', '/ce_soir', '/telescopes', '/mission-control', '/globe',
    '/telemetrie-sondes', '/sky-camera', '/orbital-radio', '/iss-tracker',
    '/visiteurs-live', '/guide-stellaire', '/oracle-cosmique', '/meteo-spatiale',
    '/aurores', '/orbital-map',
}

# ── Owner IPs : cache in-memory rechargé toutes les 5 min ───────────────────


# PASS 26.2 (2026-05-08) — @app.before_request _astroscan_request_timing_start supprimé.
# Source de vérité : app/hooks.py (registered via app/__init__.py:_register_hooks
# et station_web.py PASS 25.5 fallback safety).


# PASS 26.1 (2026-05-08) — @app.before_request _astroscan_visitor_session_before supprimé.
# Source de vérité : app/hooks.py (registered via app/__init__.py:_register_hooks
# et station_web.py PASS 25.5 fallback safety).


# PASS 26.2 (2026-05-08) — @app.before_request _maybe_increment_visits supprimé.
# Source de vérité : app/hooks.py (registered via app/__init__.py:_register_hooks
# et station_web.py PASS 25.5 fallback safety).


# ─── PASS 26.3 ─── @app.after_request _astroscan_struct_log_response
# Hook supprimé du monolithe — désormais servi exclusivement par app/hooks.py
# (register_all_for_fallback prend le relais en mode fallback PASS 25.5)


# ─── LANGUE / i18n ─────────────────────────────────────────────────────────
SUPPORTED_LANGS = {"fr", "en"}

def get_user_lang():
    """Priorité : cookie > Accept-Language header > défaut fr."""
    lang = request.cookies.get("lang", "")
    if lang in SUPPORTED_LANGS:
        return lang
    accept = request.headers.get("Accept-Language", "")
    return "en" if accept.lower().startswith("en") else "fr"

# ─── API PUBLIQUE — DOCUMENTATION ──────────────────────────────────────────
API_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "AstroScan-Chohra API",
        "version": "2.0.0",
        "description": (
            "API publique de la station d'observation spatiale AstroScan-Chohra. "
            "Données en temps réel : ISS, météo spatiale, éphémérides Tlemcen, APOD NASA. "
            "Usage scientifique et éducatif libre."
        ),
        "contact": {
            "name": "Zakaria Chohra",
            "email": "zakaria.chohra@gmail.com",
            "url": "https://astroscan.space/a-propos"
        },
        "license": {
            "name": "Open Data — Usage scientifique et éducatif",
            "url": "https://astroscan.space/a-propos"
        }
    },
    "servers": [{"url": "https://astroscan.space", "description": "Production"}],
    "paths": {
        "/api/ephemerides/tlemcen": {
            "get": {
                "summary": "Éphémérides Tlemcen",
                "description": "Données astronomiques en temps réel depuis Tlemcen (34.88°N, 1.32°E, 800m). Soleil (lever/coucher), Lune (phase, illumination), planètes visibles, début/fin nuit astronomique. Cache 5 min.",
                "tags": ["Astronomie"],
                "responses": {"200": {"description": "JSON éphémérides complètes"}}
            }
        },
        "/api/iss": {
            "get": {
                "summary": "Position ISS en temps réel",
                "description": "Coordonnées GPS de la Station Spatiale Internationale, altitude, vitesse, pays survolé.",
                "tags": ["ISS"],
                "responses": {"200": {"description": "JSON position ISS"}}
            }
        },
        "/api/passages-iss": {
            "get": {
                "summary": "Passages ISS sur Tlemcen",
                "description": "Prochains passages visibles de l'ISS au-dessus de Tlemcen avec azimut, élévation max et durée.",
                "tags": ["ISS"],
                "parameters": [
                    {"name": "lat", "in": "query", "schema": {"type": "number"}, "example": 34.88},
                    {"name": "lon", "in": "query", "schema": {"type": "number"}, "example": 1.32}
                ],
                "responses": {"200": {"description": "JSON passages ISS"}}
            }
        },
        "/api/apod": {
            "get": {
                "summary": "APOD NASA du jour",
                "description": "Image astronomique du jour NASA avec titre, explication et traduction française automatique.",
                "tags": ["NASA"],
                "responses": {"200": {"description": "JSON APOD"}}
            }
        },
        "/api/meteo-spatiale": {
            "get": {
                "summary": "Météo spatiale NOAA",
                "description": "Indice Kp, alertes géomagnétiques, vent solaire, probabilité aurores boréales.",
                "tags": ["Météo Spatiale"],
                "responses": {"200": {"description": "JSON météo spatiale"}}
            }
        },
        "/api/aurore": {
            "get": {
                "summary": "Données aurores boréales",
                "description": "Niveau d'activité aurorale, prévisions Kp 24h, visibilité par latitude.",
                "tags": ["Météo Spatiale"],
                "responses": {"200": {"description": "JSON aurores"}}
            }
        },
        "/api/tonight": {
            "get": {
                "summary": "Objets observables ce soir",
                "description": "Objets du ciel profond visibles depuis Tlemcen cette nuit — calculés avec astropy. Inclut phase lunaire.",
                "tags": ["Astronomie"],
                "responses": {"200": {"description": "JSON objets de la nuit"}}
            }
        },
        "/api/moon": {
            "get": {
                "summary": "Phase lunaire actuelle",
                "description": "Phase, illumination (%), jour du cycle lunaire.",
                "tags": ["Astronomie"],
                "responses": {"200": {"description": "JSON phase lune"}}
            }
        },
        "/api/visitors/snapshot": {
            "get": {
                "summary": "Statistiques visiteurs",
                "description": "Nombre total de visiteurs, visiteurs actifs, pays distincts, top pays, humains vs robots.",
                "tags": ["Analytics"],
                "parameters": [
                    {"name": "exclude_my_ip", "in": "query", "schema": {"type": "string", "default": "1"}, "description": "Exclure l'IP du serveur"}
                ],
                "responses": {"200": {"description": "JSON stats visiteurs"}}
            }
        },
        "/api/health": {
            "get": {
                "summary": "Santé de l'API",
                "description": "Statut de tous les modules : TLE, APOD, ISS, SDR, base de données.",
                "tags": ["Système"],
                "responses": {"200": {"description": "JSON health check"}}
            }
        },
        "/api/export/visitors.csv": {
            "get": {
                "summary": "Export visiteurs CSV",
                "description": "Statistiques visiteurs par pays au format CSV. Données anonymisées — aucune donnée personnelle.",
                "tags": ["Export"],
                "responses": {"200": {"description": "CSV file — country, country_code, visits, first_visit, last_visit"}}
            }
        },
        "/api/export/visitors.json": {
            "get": {
                "summary": "Export visiteurs JSON",
                "description": "Statistiques visiteurs par pays avec métadonnées de citation scientifique (CC BY 4.0).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON avec metadata de citation"}}
            }
        },
        "/api/export/ephemerides.json": {
            "get": {
                "summary": "Export éphémérides JSON",
                "description": "Éphémérides Tlemcen complètes avec métadonnées scientifiques (coordonnées, licence, computation).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON scientifique avec metadata"}}
            }
        },
        "/api/export/observations.json": {
            "get": {
                "summary": "Export observations stellaires",
                "description": "Archive 1500+ observations avec analyse IA (objets détectés, anomalies, score confiance).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON observations archive"}}
            }
        },
        "/api/export/apod-history.json": {
            "get": {
                "summary": "Export APOD + traductions FR",
                "description": "Historique NASA APOD avec traductions françaises (CC BY 4.0).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON APOD archive"}}
            }
        },
        "/sitemap.xml": {
            "get": {
                "summary": "Sitemap SEO dynamique",
                "description": "Sitemap XML avec toutes les pages indexables, lastmod = date du jour.",
                "tags": ["SEO"],
                "responses": {"200": {"description": "XML sitemap"}}
            }
        }
    },
    "tags": [
        {"name": "ISS", "description": "Station Spatiale Internationale"},
        {"name": "Astronomie", "description": "Éphémérides et données astronomiques"},
        {"name": "NASA", "description": "Données officielles NASA"},
        {"name": "Météo Spatiale", "description": "NOAA, Kp-index, aurores boréales"},
        {"name": "Analytics", "description": "Statistiques plateforme"},
        {"name": "Export", "description": "Téléchargement données CSV/JSON — CC BY 4.0"},
        {"name": "Système", "description": "Health checks et statut"},
        {"name": "SEO", "description": "Référencement"}
    ]
}

# ────────────────────────────────────────────────────────────────────────────










# ══════════════════════════════════════════════════════════════
# PAGES
# ══════════════════════════════════════════════════════════════

# MIGRATED TO pages_bp PASS 5 — / → see app/blueprints/pages/__init__.py (index)
# MIGRATED TO pages_bp PASS 5 — /portail → see app/blueprints/pages/__init__.py (portail)
# MIGRÉ → app/blueprints/pages/__init__.py (PASS 3) — /landing
# MIGRATED TO pages_bp PASS 5 — /technical → see app/blueprints/pages/__init__.py (technical_page)
# MIGRATED TO pages_bp PASS 5 — /dashboard → see app/blueprints/pages/__init__.py (dashboard)


# PASS 27.7 (2026-05-09) — Analytics helpers déplacés vers source de vérité unique
# app/services/analytics_dashboard.py (les 6 fonctions étaient utilisées par
# load_analytics_readonly() sans y être importées — bug latent depuis PASS 16
# corrigé par effet de bord). Re-exportés ici pour conformité au pattern
# strangler fig (aucun consommateur externe via `from station_web import _analytics_*`
# détecté à ce jour, mais maintenu par défensive).
from app.services.analytics_dashboard import (  # noqa: F401 (re-export)
    _analytics_tz_for_country_code,
    _analytics_fmt_duration_sec,
    _analytics_journey_display,
    _analytics_start_local_display,
    _analytics_time_hms_local,
    _analytics_session_classification,
)


# PASS 20.1 (2026-05-08) — Visitors helpers extracted to app/services/visitors_helpers.py
# Shim re-exports for backward compatibility (les blueprints / services existants
# importent encore depuis station_web : `from station_web import get_geo_from_ip`).
from app.services.visitors_helpers import (  # noqa: E402,F401
    _compute_human_score,
    _get_db_visitors,
    _get_visits_count,
    _increment_visits,
    _invalidate_owner_ips_cache,
    _register_unique_visit_from_request,
    get_global_stats,
    get_geo_from_ip,
)




# MIGRATED TO analytics_bp PASS 16 — /analytics → see app/blueprints/analytics/__init__.py (analytics_dashboard)
# Helpers _load_analytics_readonly + _analytics_empty_payload extraits → app/services/analytics_dashboard.py


# MIGRATED TO pages_bp PASS 5 — /overlord_live → see app/blueprints/pages/__init__.py (overlord_live)
# MIGRATED TO pages_bp PASS 5 — /galerie → see app/blueprints/pages/__init__.py (galerie)
# MIGRATED TO pages_bp PASS 5 — /observatoire → see app/blueprints/pages/__init__.py (observatoire)


# MIGRATED TO pages_bp PASS 5 — /vision-2026 → see app/blueprints/pages/__init__.py (vision_2026)
# MIGRATED TO pages_bp PASS 5 — /sondes → see app/blueprints/pages/__init__.py (sondes)
# MIGRATED TO pages_bp PASS 5 — /telemetrie-sondes → see app/blueprints/pages/__init__.py (telemetrie_sondes)


# MIGRATED TO cameras_bp PASS 6 — /sky-camera → see app/blueprints/cameras/__init__.py (sky_camera)
# MIGRATED TO cameras_bp PASS 6 — /api/sky-camera/analyze → see app/blueprints/cameras/__init__.py (api_sky_camera_analyze)


# MIGRATED TO cameras_bp PASS 15 — /api/sky-camera/simulate → see app/blueprints/cameras/__init__.py (api_sky_camera_simulate)


# MIGRATED TO feeds_bp PASS 11 — /api/sondes/live → see app/blueprints/feeds/__init__.py (api_sondes_live)




# ══════════════════════════════════════════════════════════════
# API — DONNÉES PRINCIPALES
# ══════════════════════════════════════════════════════════════

# PASS 27.8 (2026-05-09) — APOD/Hubble fetchers déplacés vers source de vérité
# unique app/services/telescope_sources.py (extrait au PASS 9, mais doublon
# laissé en place dans le monolithe — supprimé en PASS 27.8 comme PASS 27.6
# l'a fait pour _curl_*).
#
# Note : le brief PASS 27.8 ciblait `external_feeds.py` mais telescope_sources.py
# contient déjà ces 4 fonctions à l'identique depuis PASS 9 et est consommé par
# app/blueprints/telescope/__init__.py:37-41. Re-exporter depuis cette source
# existante évite un nouveau doublon (cf. /tmp/PASS_27_8_INVENTORY.md pour la
# justification complète).
#
# Aucun consommateur externe via `from station_web import _fetch_*` détecté à
# ce jour, ni d'appel interne au monolithe. Re-export maintenu par défensive.
from app.services.telescope_sources import (  # noqa: F401 (re-export)
    _IMAGE_CACHE_TTL,
    _source_path,
    _fetch_apod_live,
    _fetch_hubble_archive,
    _fetch_hubble_live,
    _fetch_apod_archive_live,
)

# État de synchronisation PC ↔ Android (source télescope affichée)
SYNC_STATE_F = Path(f'{STATION}/telescope_live/sync_state.json')
def _sync_state_read():
    try:
        if SYNC_STATE_F.exists():
            with open(SYNC_STATE_F) as f:
                d = json.load(f)
                s = (d.get('source') or 'live').strip().lower()
                if s in ('live', 'apod', 'hubble', 'apod_archive'):
                    return s
    except Exception:
        pass
    return 'live'
def _sync_state_write(source):
    s = (source or 'live').strip().lower()
    if s not in ('live', 'apod', 'hubble', 'apod_archive'):
        s = 'live'
    try:
        SYNC_STATE_F.parent.mkdir(parents=True, exist_ok=True)
        SYNC_STATE_F.write_text(json.dumps({'source': s, 'updated': time.time()}, ensure_ascii=False))
    except Exception as e:
        log.warning(f"sync_state write: {e}")
    return s

# MIGRATED TO system_bp PASS 4 — /api/sync/state GET → see app/blueprints/system/__init__.py
# MIGRATED TO system_bp PASS 4 — /api/sync/state POST → see app/blueprints/system/__init__.py
# MIGRATED TO system_bp PASS 4 — /api/telescope/sources → see app/blueprints/system/__init__.py
# FIX PASS 9: décorateurs orphelins commentés (étaient suspendus sur api_telescope_live)

# MIGRATED TO cameras_bp PASS 6 — /api/observatory/status → see app/blueprints/cameras/__init__.py (api_observatory_status)
# MIGRATED TO cameras_bp PASS 6 — /observatory/status → see app/blueprints/cameras/__init__.py (observatory_status_page)


# MIGRATED TO ai_bp PASS 10 — /api/telescope/live → see app/blueprints/ai/__init__.py (api_telescope_live)
# (différé PASS 9 levé : utilise _gemini_translate + _call_claude depuis app.services.ai_translate)

# MIGRATED TO telescope_bp PASS 9 — /api/image → see app/blueprints/telescope/__init__.py (api_image)
# MIGRATED TO telescope_bp PASS 9 — /api/title → see app/blueprints/telescope/__init__.py (api_title)
# Helpers _source_path, _fetch_apod_live, _fetch_hubble_live, _fetch_apod_archive_live,
# _IMAGE_CACHE_TTL extraits → app/services/telescope_sources.py

# ══════════════════════════════════════════════════════════════
# API — ISS
# ══════════════════════════════════════════════════════════════

# PASS 23 — moved to app/services/iss_live.py
from app.services.iss_live import _fetch_iss_live  # noqa: F401 (re-export)


def _get_iss_tle_from_cache():
    # moved to app/services/tle.py (get_iss_tle_from_sources)
    """Retourne (tle1, tle2) ISS depuis TLE_CACHE si disponible."""
    try:
        items = (TLE_CACHE or {}).get("items") or []
        for item in items:
            name = str(item.get("name") or "").upper()
            if "ISS" in name or "ZARYA" in name:
                tle1 = str(
                    item.get("line1")
                    or item.get("tle1")
                    or item.get("tle_line1")
                    or ""
                ).strip()
                tle2 = str(
                    item.get("line2")
                    or item.get("tle2")
                    or item.get("tle_line2")
                    or ""
                ).strip()
                if tle1 and tle2:
                    _emit_diag_json(
                        {
                            "event": "iss_tle_loaded",
                            "name": item.get("name"),
                            "tle1_len": len(tle1),
                            "tle2_len": len(tle2),
                        }
                    )
                    return tle1, tle2
    except Exception as e:
        _emit_diag_json(
            {
                "event": "iss_tle_missing",
                "reason": f"exception:{e}",
            }
        )
    # Fallback TLE: scanner le fichier complet (le cache items peut être tronqué à 1000 entrées).
    try:
        if os.path.isfile(TLE_ACTIVE_PATH):
            all_items = _parse_tle_file(TLE_ACTIVE_PATH)
            for item in all_items:
                name = str(item.get("name") or "").upper()
                if "ISS" in name or "ZARYA" in name:
                    tle1 = str(item.get("line1") or "").strip()
                    tle2 = str(item.get("line2") or "").strip()
                    if tle1 and tle2:
                        _emit_diag_json(
                            {
                                "event": "iss_tle_loaded",
                                "name": item.get("name"),
                                "source": "tle_active_file",
                                "tle1_len": len(tle1),
                                "tle2_len": len(tle2),
                            }
                        )
                        return tle1, tle2
    except Exception as e:
        _emit_diag_json(
            {
                "event": "iss_tle_missing",
                "reason": f"file_scan_exception:{e}",
            }
        )

    _emit_diag_json(
        {
            "event": "iss_tle_missing",
            "tle_items_count": len((TLE_CACHE or {}).get("items") or []),
        }
    )
    return None, None


# MIGRATED TO iss_bp PASS 16 — /api/iss → see app/blueprints/iss/routes.py (api_iss)
# Helpers monolithe (system_log, _fetch_iss_live, _get_iss_crew, propagate_tle_debug,
# TLE_CACHE, TLE_ACTIVE_PATH, _parse_tle_file, _emit_diag_json) accédés via lazy import.






def _get_satellite_tle_by_name(target_name):
    target_upper = str(target_name or "").upper()
    canonical = get_satellite_tle_name_map().get(target_upper, target_upper)

    for item in (TLE_CACHE or {}).get("items") or []:
        name = str(item.get("name") or "").upper()
        if name == canonical.upper():
            tle1 = str(item.get("line1") or item.get("tle1") or "").strip()
            tle2 = str(item.get("line2") or item.get("tle2") or "").strip()
            if tle1 and tle2:
                return tle1, tle2, str(item.get("name") or canonical)

    if os.path.isfile(TLE_ACTIVE_PATH):
        for item in _parse_tle_file(TLE_ACTIVE_PATH):
            name = str(item.get("name") or "").upper()
            if name == canonical.upper():
                tle1 = str(item.get("line1") or "").strip()
                tle2 = str(item.get("line2") or "").strip()
                if tle1 and tle2:
                    return tle1, tle2, str(item.get("name") or canonical)

    return None, None, canonical


# MIGRATED TO satellites_bp PASS 14 — /api/satellite/<name> → see app/blueprints/satellites/__init__.py (api_satellite)




# MIGRATED TO weather_bp PASS 7 — /api/meteo-spatiale → see app/blueprints/weather/__init__.py (api_meteo_spatiale)
# MIGRATED TO weather_bp PASS 7 — /meteo-spatiale → see app/blueprints/weather/__init__.py (meteo_spatiale_page)


# MIGRATED TO iss_bp PASS 11 — /api/passages-iss → see app/blueprints/iss/routes.py (api_passages_iss)


# MIGRATED TO feeds_bp PASS 8 — /api/voyager-live → see app/blueprints/feeds/__init__.py (api_voyager_live)


def _fetch_iss_crew():
    """Lecture brute du nombre d'astronautes à bord de l'ISS via open-notify."""
    raw = _curl_get('http://api.open-notify.org/astros.json', timeout=6)
    if not raw:
        return 7
    try:
        data = json.loads(raw)
        iss = [p for p in data.get('people', []) if p.get('craft') == 'ISS']
        return len(iss) if iss else data.get('number', 7)
    except Exception:
        return 7


def _get_iss_crew():
    """
    Nombre d'astronautes à bord de l'ISS avec cache serveur 5 min.
    On interroge la source officielle une seule fois toutes les 5 minutes,
    puis PC et Android partagent la même valeur.
    """
    crew = get_cached('iss_crew', 300, _fetch_iss_crew)
    try:
        crew = int(crew)
        if crew <= 0 or crew > 20:
            crew = 7
    except Exception:
        crew = 7
    return crew

def _guess_region(lat, lon):
    """Estimation grossière de la région survolée."""
    if -60 < lat < 60:
        if -30 < lon < 60:
            return 'Afrique / Europe'
        elif 60 < lon < 150:
            return 'Asie'
        elif -150 < lon < -30:
            return 'Amériques'
        else:
            return 'Océan Pacifique'
    elif lat >= 60:
        return 'Arctique'
    else:
        return 'Antarctique'

# ══════════════════════════════════════════════════════════════
# API — CHAT AEGIS (rotation clés + cache 5 min + délai 4s + curl)
# ══════════════════════════════════════════════════════════════


# MIGRATED TO ai_bp PASS 10 — /api/chat → see app/blueprints/ai/__init__.py (api_chat)


# MIGRATED TO ai_bp PASS 10 — /api/aegis/chat → see app/blueprints/ai/__init__.py (api_aegis_chat)
# MIGRATED TO ai_bp PASS 10 — /api/aegis/status → see app/blueprints/ai/__init__.py (api_aegis_status)
# MIGRATED TO ai_bp PASS 10 — /api/aegis/groq-ping → see app/blueprints/ai/__init__.py (api_aegis_groq_ping)
# MIGRATED TO ai_bp PASS 10 — /api/aegis/claude-test → see app/blueprints/ai/__init__.py (api_aegis_claude_test)


# ══════════════════════════════════════════════════════════════
# API — TRANSLATE
# ══════════════════════════════════════════════════════════════

# MIGRATED TO ai_bp PASS 10 — /api/translate → see app/blueprints/ai/__init__.py (api_translate)
# MIGRATED TO ai_bp PASS 10 — /api/astro/explain → see app/blueprints/ai/__init__.py (api_astro_explain)

# ══════════════════════════════════════════════════════════════
# API — TELESCOPE HUB
# ══════════════════════════════════════════════════════════════

# MIGRATED TO telescope_bp PASS 9 — /api/telescope-hub → see app/blueprints/telescope/__init__.py (api_telescope_hub)

# ══════════════════════════════════════════════════════════════
# API — SHIELD
# ══════════════════════════════════════════════════════════════

# MIGRATED TO archive_bp PASS 6 — /api/shield → see app/blueprints/archive/__init__.py (api_shield)
# MIGRATED TO archive_bp PASS 6 — /api/classification/stats → see app/blueprints/archive/__init__.py (api_classification_stats)
# MIGRATED TO archive_bp PASS 6 — /api/mast/targets → see app/blueprints/archive/__init__.py (api_mast_targets)

# ══════════════════════════════════════════════════════════════
# API — SDR
# ══════════════════════════════════════════════════════════════

# MIGRATED TO sdr_bp PASS 14 — /api/sdr/captures → see app/blueprints/sdr/routes.py (api_sdr_captures)

# ══════════════════════════════════════════════════════════════
# API — NASA SkyView (Goddard / HEASARC, gratuit, sans compte)
# ══════════════════════════════════════════════════════════════
try:
    from skyview_module import fetch_skyview_image, fetch_multiple_surveys, TARGETS as SKYVIEW_TARGETS, SURVEYS as SKYVIEW_SURVEYS
except ImportError:
    SKYVIEW_TARGETS = {}
    SKYVIEW_SURVEYS = {}
    def fetch_skyview_image(*a, **k):
        return {'ok': False, 'error': 'skyview_module non disponible'}
    def fetch_multiple_surveys(*a, **k):
        return []

# MIGRATED TO cameras_bp PASS 6 — /api/skyview/targets → see app/blueprints/cameras/__init__.py (skyview_targets)
# MIGRATED TO cameras_bp PASS 6 — /api/skyview/fetch → see app/blueprints/cameras/__init__.py (skyview_fetch)
# MIGRATED TO cameras_bp PASS 6 — /api/skyview/multiwave/<target_id> → see app/blueprints/cameras/__init__.py (skyview_multiwave)
# MIGRATED TO cameras_bp PASS 6 — /api/skyview/list → see app/blueprints/cameras/__init__.py (skyview_list)

# ══════════════════════════════════════════════════════════════
# PWA — Service Worker & Manifest
# ══════════════════════════════════════════════════════════════

# MIGRATED TO main_bp PASS 5 — /sw.js → see app/blueprints/main/__init__.py (sw_js)
# MIGRATED TO main_bp PASS 5 — /manifest.json → see app/blueprints/main/__init__.py (manifest_json)
# MIGRATED TO main_bp PASS 5 — /api/push/subscribe → see app/blueprints/main/__init__.py (api_push_subscribe)

# ══════════════════════════════════════════════════════════════
# STATIC
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# PAGE /ce_soir + APIs associées (Ce soir & news)
# ══════════════════════════════════════════════════════════════

# Fêtes islamiques (année grégorienne 2026 / hégirien 1447–1448) — module El Hilal /ce_soir
FETES_ISLAMIQUES = [
    {
        "nom": "1er Mouharram",
        "nom_ar": "رأس السنة الهجرية",
        "description": "Nouvel An hégirien — début de l'année 1448",
        "date_2026": "2026-06-17",
        "hijri": "1 Mouharram 1448",
    },
    {
        "nom": "Achoura",
        "nom_ar": "عاشوراء",
        "description": "10ème jour de Mouharram — jour de jeûne recommandé",
        "date_2026": "2026-06-26",
        "hijri": "10 Mouharram 1448",
    },
    {
        "nom": "Mawlid Ennabawi",
        "nom_ar": "المولد النبوي الشريف",
        "description": "Naissance du Prophète Muhammad ﷺ",
        "date_2026": "2026-09-13",
        "hijri": "12 Rabi al-Awwal 1448",
    },
]


# MIGRATED TO pages_bp PASS 5 — /ce_soir → see app/blueprints/pages/__init__.py (ce_soir_page)






# MIGRATED TO cameras_bp PASS 6 — /visiteurs-live → see app/blueprints/cameras/__init__.py (visiteurs_live_page)
# MIGRATED TO cameras_bp PASS 6 — /api/audio-proxy → see app/blueprints/cameras/__init__.py (api_audio_proxy)


# ══════════════════════════════════════════════════════════════
# GUIDE TOURISTIQUE STELLAIRE (Claude + éphémérides)
# ══════════════════════════════════════════════════════════════

# MIGRATED TO ai_bp PASS 10 — /guide-stellaire → see app/blueprints/ai/__init__.py (guide_stellaire_page)
# MIGRATED TO ai_bp PASS 10 — /oracle-cosmique → see app/blueprints/ai/__init__.py (oracle_cosmique_page)


# MIGRATED TO ai_bp PASS 17 — /api/oracle-cosmique POST → see app/blueprints/ai/__init__.py (api_oracle_cosmique)
# Helpers _oracle_*, ORACLE_COSMIQUE_SYSTEM extraits → app/services/oracle_engine.py


# MIGRATED TO ai_bp PASS 10 — /api/guide-geocode → see app/blueprints/ai/__init__.py (api_guide_geocode)


# MIGRATED TO ai_bp PASS 17 — /api/guide-stellaire POST → see app/blueprints/ai/__init__.py (api_guide_stellaire)
# Orchestration extraite → app/services/guide_engine.py (build_orbital_guide)


# MIGRATED TO weather_bp PASS 7 — /aurores → see app/blueprints/weather/__init__.py (aurores_page)
# MIGRATED TO weather_bp PASS 7 — /api/aurore → see app/blueprints/weather/__init__.py (api_aurore)


# MIGRATED TO weather_bp PASS 7 — /api/weather → see app/blueprints/weather/__init__.py (api_weather_alias)
# MIGRATED TO weather_bp PASS 7 — /api/weather/local → see app/blueprints/weather/__init__.py (api_weather_local)


# MIGRATED TO weather_bp PASS 7 — /api/weather/bulletins → see app/blueprints/weather/__init__.py (api_weather_bulletins)
# MIGRATED TO weather_bp PASS 7 — /api/weather/bulletins/latest → see app/blueprints/weather/__init__.py (api_weather_bulletins_latest)
# MIGRATED TO weather_bp PASS 7 — /api/weather/history → see app/blueprints/weather/__init__.py (api_weather_history)
# MIGRATED TO weather_bp PASS 7 — /api/weather/bulletins/save → see app/blueprints/weather/__init__.py (api_weather_bulletins_save)


# MIGRATED TO feeds_bp PASS 14 — /api/apod alias → see app/blueprints/feeds/__init__.py (api_apod_alias)


# MIGRATED TO ai_bp PASS 15 — /api/oracle alias → see app/blueprints/ai/__init__.py (api_oracle_alias)


# MIGRATED TO weather_bp PASS 7 — /api/aurores → see app/blueprints/weather/__init__.py (api_aurores_alias)


# MIGRATED TO api_bp PASS 11 — /api/catalog → see app/blueprints/api/__init__.py (api_catalog)
# MIGRATED TO api_bp PASS 11 — /api/catalog/<obj_id> → see app/blueprints/api/__init__.py (api_catalog_object)


# MIGRATED TO astro_bp PASS 7 — /api/tonight → see app/blueprints/astro/__init__.py (api_tonight)
# MIGRATED TO astro_bp PASS 7 — /api/moon → see app/blueprints/astro/__init__.py (api_moon)
# MIGRATED TO astro_bp PASS 7 — /api/ephemerides/tlemcen → see app/blueprints/astro/__init__.py (api_ephemerides_tlemcen)


# MIGRATED TO api_bp PASS 11 — /api/v1/iss → see app/blueprints/api/__init__.py (api_v1_iss)


# MIGRATED TO api_bp PASS 11 — /api/v1/planets → see app/blueprints/api/__init__.py (api_v1_planets)


# MIGRATED TO api_bp PASS 11 — /api/v1/catalog → see app/blueprints/api/__init__.py (api_v1_catalog)


# MIGRATED TO archive_bp PASS 6 — /api/microobservatory → see app/blueprints/archive/__init__.py (api_microobservatory)




# MIGRATED TO cameras_bp PASS 15 — /api/microobservatory/images → see app/blueprints/cameras/__init__.py (api_microobservatory_images)
# MIGRATED TO cameras_bp PASS 15 — /api/microobservatory/preview/<nom_fichier> → see app/blueprints/cameras/__init__.py (api_microobservatory_preview)
# Helper _fetch_microobservatory_images extrait → app/services/microobservatory.py


# PASS 27.9 (2026-05-09) — Microobservatory pipeline (3 constantes + 4 helpers)
# déplacé vers source de vérité unique app/services/microobservatory.py.
# Re-exporté ici pour préserver le lazy import de telescope_helpers.py:35-41
# (`from station_web import _mo_fetch_catalog_today, _mo_fits_to_jpg,
# _mo_visible_tonight, cache_set, log` — pattern PASS 20.4 cycle-safe).
from app.services.microobservatory import (  # noqa: F401 (re-export)
    _MO_DIR_URL,
    _MO_DL_BASE,
    _MO_OBJECT_CATALOG,
    _mo_parse_filename,
    _mo_fetch_catalog_today,
    _mo_visible_tonight,
    _mo_fits_to_jpg,
)


# PASS 20.4 (2026-05-08) — Telescope helpers extracted to app/services/telescope_helpers.py
# Shim re-export for backward compatibility (telescope_bp utilise
# `from station_web import _telescope_nightly_tlemcen` via lazy import.)
# Le corps original (97 lignes) a été déplacé verbatim vers telescope_helpers.py
# avec lazy imports inside pour log/_mo_*/cache_set (cycle-safe).
from app.services.telescope_helpers import _telescope_nightly_tlemcen  # noqa: E402,F401


# MIGRATED TO telescope_bp PASS 9 — /api/telescope/nightly → see app/blueprints/telescope/__init__.py (api_telescope_nightly)


# MIGRATED TO telescope_bp PASS 16 — /api/telescope/trigger-nightly POST → see app/blueprints/telescope/__init__.py (api_telescope_trigger_nightly)
# Helper _telescope_nightly_tlemcen (~100L + _mo_* helpers FITS+JPG) reste en monolithe — accédé via lazy import.


# MIGRATED TO cameras_bp PASS 6 — /telescope_live/<path:filename> → see app/blueprints/cameras/__init__.py (serve_telescope_live_img)


# MIGRATED TO telescope_bp PASS 9 — /mission-control → see app/blueprints/telescope/__init__.py (mission_control)
# MIGRATED TO telescope_bp PASS 9 — /api/mission-control → see app/blueprints/telescope/__init__.py (api_mission_control)


# MIGRATED TO astro_bp PASS 7 — /api/astro/object → see app/blueprints/astro/__init__.py (api_astro_object)

# MIGRATED TO feeds_bp PASS 8 — /api/news → see app/blueprints/feeds/__init__.py (api_news)

# ══════════════════════════════════════════════════════════════
# FLUX SPATIAUX — Voyager JPL, NEO, Vent solaire, Mars, APOD, Alertes solaires (curl)
# Toutes les requêtes passent par _curl_get (urllib bloqué serveur Tlemcen).
#
# URLs officielles utilisées:
#   Voyager 1/2:  https://ssd.jpl.nasa.gov/api/horizons.api (COMMAND -31 / -32)
#   Vent solaire: https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json
#   Alertes SWPC: https://services.swpc.noaa.gov/json/alerts.json
#                 https://services.swpc.noaa.gov/json/xray-flares-latest.json
#   ISS:          https://api.wheretheiss.at/v1/satellites/25544
#   Mars photos:  https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/latest_photos
#   APOD:         https://api.nasa.gov/planetary/apod
# ══════════════════════════════════════════════════════════════

from datetime import datetime as _dt_utc, timezone as _tz_utc


# MIGRATED TO api_bp PASS 11 — /api/v1/asteroids → see app/blueprints/api/__init__.py (api_v1_asteroids)


# MIGRATED TO weather_bp PASS 7 — /api/v1/solar-weather → see app/blueprints/weather/__init__.py (api_v1_solar)
# MIGRATED TO astro_bp PASS 7 — /api/v1/tonight → see app/blueprints/astro/__init__.py (api_v1_tonight)


def _fetch_voyager():
    """Position Voyager 1 & 2 via NASA JPL Horizons (curl)."""
    try:
        now = _dt_utc.now(_tz_utc.utc)
        y, mo, d = now.year, now.month, now.day
        results = {}
        for name, target in [('VOYAGER_1', '-31'), ('VOYAGER_2', '-32')]:
            url = (
                f"https://ssd.jpl.nasa.gov/api/horizons.api?"
                f"format=text&COMMAND='{target}'&OBJ_DATA=YES&MAKE_EPHEM=YES"
                f"&EPHEM_TYPE=VECTORS&CENTER='500@10'"
                f"&START_TIME='{y}-{mo:02d}-{d:02d}'&STOP_TIME='{y}-{mo:02d}-{d:02d}T23:59'"
                f"&STEP_SIZE='1d'&QUANTITIES='20'"
            )
            raw = _curl_get(url, timeout=20)
            if not raw:
                continue
            dist_au = None
            speed_km_s = None
            rg_match = re.search(r'RG=\s*([\d.]+)', raw)
            if rg_match:
                dist_au = float(rg_match.group(1))
            rr_match = re.search(r'RR=\s*([-\d.]+)', raw)
            if rr_match:
                speed_au_d = float(rr_match.group(1))
                speed_km_s = abs(speed_au_d * 1731.46)
            if dist_au is not None:
                results[name] = {
                    'dist_au': round(dist_au, 4),
                    'dist_km': round(dist_au * 149597870.7),
                    'speed_km_s': round(speed_km_s, 2) if speed_km_s else None,
                    'source': 'NASA JPL Horizons',
                }
        return results if results else None
    except Exception as e:
        log.warning(f"voyager: {e}")
        return None

def _fetch_neo():
    """Astéroïdes NEO du jour via NASA NeoWs API (curl)."""
    try:
        nasa_key = os.environ.get('NASA_API_KEY', 'DEMO_KEY')
        today = _dt_utc.now(_tz_utc.utc).date().isoformat()
        url = f"https://api.nasa.gov/neo/rest/v1/feed?start_date={today}&end_date={today}&api_key={nasa_key}"
        raw = _curl_get(url, timeout=20)
        if not raw:
            return None
        data = _safe_json_loads(raw, "neo")
        if not isinstance(data, dict):
            return None
        neos = []
        for date_key, objects in data.get('near_earth_objects', {}).items():
            for obj in (objects or [])[:8]:
                ca = (obj.get('close_approach_data') or [{}])[0]
                dist_au = ca.get('miss_distance', {}).get('astronomical', '?')
                dist_km = ca.get('miss_distance', {}).get('kilometers', '?')
                vel = ca.get('relative_velocity', {}).get('kilometers_per_second', 0)
                try:
                    vel = round(float(vel), 2)
                except (TypeError, ValueError):
                    vel = 0
                diam = obj.get('estimated_diameter', {}).get('meters', {}) or {}
                diam_min = round(float(diam.get('estimated_diameter_min', 0)))
                diam_max = round(float(diam.get('estimated_diameter_max', 0)))
                neos.append({
                    'name': obj.get('name', ''),
                    'dist_au': dist_au,
                    'dist_km': dist_km,
                    'vel_km_s': vel,
                    'diam_min': diam_min,
                    'diam_max': diam_max,
                    'hazardous': obj.get('is_potentially_hazardous_asteroid', False),
                    'date': ca.get('close_approach_date', today),
                })
        neos.sort(key=lambda x: (float(x['dist_au']) if x['dist_au'] != '?' else 999))
        return neos
    except Exception as e:
        log.warning(f"neo: {e}")
        return None

def _fetch_solar_wind():
    """Vent solaire NOAA DSCOVR temps réel (curl)."""
    try:
        url = "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json"
        raw = _curl_get(url, timeout=15)
        if not raw:
            return None
        data = _safe_json_loads(raw, "solar_wind")
        if not isinstance(data, list) or len(data) < 2:
            return None
        latest = data[-1]
        return {
            'timestamp': latest[0],
            'density': latest[1],
            'speed': latest[2],
            'temperature': latest[3],
            'source': 'NOAA DSCOVR',
        }
    except Exception as e:
        log.warning(f"solar_wind: {e}")
        return None

def _fetch_solar_alerts():
    """Alertes éruptions solaires et événements — NOAA SWPC (curl)."""
    try:
        # Alertes texte + derniers flares X-ray
        out = {'alerts': [], 'flares': [], 'source': 'NOAA SWPC'}
        raw = _curl_get('https://services.swpc.noaa.gov/json/alerts.json', timeout=12)
        if raw:
            data = _safe_json_loads(raw, "solar_alerts")
            if isinstance(data, list):
                out['alerts'] = [a for a in data[-10:] if isinstance(a, dict)]
            elif isinstance(data, dict) and 'alerts' in data:
                out['alerts'] = data['alerts'][-10:]
        raw2 = _curl_get('https://services.swpc.noaa.gov/json/xray-flares-latest.json', timeout=10)
        if raw2:
            data2 = _safe_json_loads(raw2, "solar_alerts_xray")
            if isinstance(data2, list):
                out['flares'] = data2[-5:]
            elif isinstance(data2, dict):
                fl = data2.get('flares', data2.get('xray_flares', [])) or []
                if isinstance(fl, list):
                    out['flares'] = fl[-5:]
        return out if (out['alerts'] or out['flares']) else None
    except Exception as e:
        log.warning(f"solar_alerts: {e}")
        return None

def _fetch_mars_rover():
    """Photos Mars Rovers (Curiosity / Perseverance) du jour — NASA API (curl)."""
    try:
        nasa_key = os.environ.get('NASA_API_KEY', 'DEMO_KEY')
        photos = []
        for rover in ['curiosity', 'perseverance']:
            try:
                url = f"https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/latest_photos?api_key={nasa_key}&page=1"
                raw = _curl_get(url, timeout=20)
                if not raw:
                    continue
                data = _safe_json_loads(raw, "mars_rover")
                if not isinstance(data, dict):
                    continue
                for p in (data.get('latest_photos') or [])[:3]:
                    photos.append({
                        'rover': rover.capitalize(),
                        'sol': p.get('sol'),
                        'date': p.get('earth_date'),
                        'camera': (p.get('camera') or {}).get('full_name', ''),
                        'img_url': p.get('img_src', ''),
                    })
            except Exception:
                continue
        return photos if photos else None
    except Exception as e:
        log.warning(f"mars_rover: {e}")
        return None

def _fetch_apod_hd():
    """APOD HD — image du jour NASA (curl)."""
    try:
        nasa_key = os.environ.get('NASA_API_KEY', 'DEMO_KEY')
        url = f"https://api.nasa.gov/planetary/apod?api_key={nasa_key}&hd=True"
        raw = _curl_get(url, timeout=15)
        if not raw:
            return None
        data = _safe_json_loads(raw, "apod_hd")
        if not isinstance(data, dict):
            return None
        img_url = data.get('hdurl') or data.get('url', '')
        if not img_url or not str(img_url).startswith('http'):
            return None
        hd_path = f'{STATION}/telescope_live/apod_hd.jpg'
        subprocess.run(['curl', '-s', '-L', '--max-time', '30', '-o', hd_path, img_url], timeout=35, capture_output=True)
        if Path(hd_path).exists():
            return {
                'title': data.get('title', ''),
                'date': data.get('date', ''),
                'explanation': (data.get('explanation') or '')[:300],
                'url': img_url,
                'hd_path': hd_path,
            }
        return {'title': data.get('title', ''), 'date': data.get('date', ''), 'url': img_url}
    except Exception as e:
        log.warning(f"apod_hd: {e}")
        return None

# MIGRATED TO feeds_bp PASS 8 — /api/feeds/voyager → see app/blueprints/feeds/__init__.py (api_feeds_voyager)
# MIGRATED TO feeds_bp PASS 8 — /api/feeds/neo → see app/blueprints/feeds/__init__.py (api_feeds_neo)
# MIGRATED TO feeds_bp PASS 8 — /api/feeds/solar → see app/blueprints/feeds/__init__.py (api_feeds_solar)
# MIGRATED TO feeds_bp PASS 8 — /api/feeds/solar_alerts → see app/blueprints/feeds/__init__.py (api_feeds_solar_alerts)
# MIGRATED TO feeds_bp PASS 8 — /api/feeds/mars → see app/blueprints/feeds/__init__.py (api_feeds_mars)
# MIGRATED TO feeds_bp PASS 8 — /api/sondes → see app/blueprints/feeds/__init__.py (api_sondes)
# MIGRATED TO feeds_bp PASS 8 — /api/feeds/apod_hd → see app/blueprints/feeds/__init__.py (api_feeds_apod_hd)
# MIGRATED TO feeds_bp PASS 8 — /api/feeds/all → see app/blueprints/feeds/__init__.py (api_feeds_all)



def _db_observations_count():
    """Nombre d'enregistrements (images / observations) dans archive_stellaire.db."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT COUNT(*) FROM observations").fetchone()
        conn.close()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


STATUS_OBSERVER_LABEL = "Tlemcen, Algérie 34.87N 1.32E"


def _fallback_status_payload_dict(now_iso):
    """Payload /status minimal si assemblage critique échoue (toujours JSON-safe)."""
    try:
        imgs = _db_observations_count()
    except Exception:
        imgs = 0
    observation_mode = "STANDARD"
    _metrics = metrics_status_fields()
    nasa_data = {}
    tle_risk = compute_tle_risk_signal("unknown")
    final_core = build_final_core(None, tle_risk, nasa_data)
    return {
        "status": "offline",
        "tle": "simulation",
        "tle_count": 0,
        "images": imgs,
        "mode": "OFFLINE_DATA",
        "uptime_seconds": int(time.time() - START_TIME),
        "last_update": now_iso,
        "passes_predicted": 0,
        "observer": STATUS_OBSERVER_LABEL,
        "data_freshness": "unknown",
        "production_mode": "OFFLINE",
        "tle_backend_status": None,
        "system_status": "offline",
        "system": {
            "status": "offline",
            "tle_status": None,
            "last_update": now_iso,
            "mode": "OFFLINE",
        },
        "errors_last_5min": _metrics["errors_last_5min"],
        "requests_per_min": _metrics["requests_per_min"],
        "stellarium": {
            "objects_detected": 0,
            "active": False,
            "last_object": None,
            "last_timestamp": None,
            "freshness": "unknown",
        },
        "observation_mode": observation_mode,
        "priority_object": None,
        "system_intelligence": build_system_intelligence(
            "offline",
            "OFFLINE",
            "unknown",
            observation_mode,
            "unknown",
            False,
            None,
        ),
        "nasa": {
            "title": None,
            "date": None,
            "image": None,
        },
        "tle_signal": {
            "risk": tle_risk,
            "freshness": "unknown",
        },
        "final_core": final_core,
    }


def _build_status_payload_dict(now_iso, include_external=True):
    """Construit le dict complet GET /status (réutilisé par self-test et introspection)."""
    uptime_seconds = int(time.time() - START_TIME)
    tle_raw = TLE_CACHE.get("status") or "simulation"
    tle_last_refresh = TLE_CACHE.get("last_refresh_iso")
    tle_source = TLE_CACHE.get("source")
    tle_error = TLE_CACHE.get("error")
    tle_count = TLE_CACHE.get("count")
    try:
        tle_n = int(tle_count) if tle_count is not None else 0
    except (TypeError, ValueError):
        tle_n = 0

    if tle_raw == "connected":
        tle_ui = "live"
    elif tle_raw == "cached":
        tle_ui = "cached"
    else:
        tle_ui = "simulation"

    last_refresh_epoch = _parse_iso_to_epoch_seconds(tle_last_refresh)
    age_sec = None if last_refresh_epoch is None else int(time.time()) - int(last_refresh_epoch)

    if age_sec is None:
        data_freshness = "unknown"
    elif age_sec <= AGING_DATA_THRESHOLD_SEC:
        data_freshness = "fresh"
    elif age_sec <= STALE_DATA_THRESHOLD_SEC:
        data_freshness = "aging"
    else:
        data_freshness = "stale"

    if tle_n <= 0:
        mode = "OFFLINE_DATA"
    elif tle_raw == "connected" and not tle_error:
        mode = "LIVE" if data_freshness != "stale" else "SIMULATION"
    elif tle_raw == "cached" and tle_n > 0:
        mode = "LIVE" if data_freshness not in ("stale", "unknown") else "SIMULATION"
    else:
        mode = "SIMULATION" if tle_n > 0 else "OFFLINE_DATA"

    if tle_n <= 0:
        status = "offline"
    elif mode == "OFFLINE_DATA":
        status = "degraded"
    elif tle_error:
        status = "degraded"
    elif data_freshness == "stale":
        status = "degraded"
    else:
        status = "ok"

    if tle_n <= 0 or status == "offline":
        production_mode = "OFFLINE"
    elif tle_raw == "connected" and not tle_error and data_freshness not in (
        "stale",
        "unknown",
    ):
        production_mode = "LIVE"
    elif tle_raw == "cached" and tle_n > 0 and data_freshness not in ("stale", "unknown"):
        production_mode = "LIVE"
    else:
        production_mode = "DEMO"

    images = _db_observations_count()
    last_update = tle_last_refresh if tle_last_refresh else now_iso

    HEALTH_STATE["app_status"] = (
        "running"
        if status == "ok"
        else ("degraded" if status == "degraded" else "offline")
    )
    HEALTH_STATE["tle_status"] = tle_raw
    HEALTH_STATE["tle_last_refresh"] = tle_last_refresh
    HEALTH_STATE["tle_source"] = tle_source
    HEALTH_STATE["uptime_seconds"] = uptime_seconds
    HEALTH_STATE["mode"] = mode

    try:
        stellarium_data = load_stellarium_data()
    except Exception as se:
        stellarium_data = []
        struct_log(
            logging.WARNING,
            category="stellarium",
            event="load_failed",
            error=str(se)[:200],
        )
    observation_mode = "LIVE_SKY" if len(stellarium_data) > 0 else "STANDARD"
    last_timestamp = None
    last_object = None
    if stellarium_data and isinstance(stellarium_data[-1], dict):
        last_object = stellarium_data[-1].get("object")
        last_timestamp = stellarium_data[-1].get("timestamp")

    freshness = compute_stellarium_freshness(last_timestamp)
    priority_object = build_priority_object(stellarium_data, freshness)
    system_intelligence = build_system_intelligence(
        status,
        production_mode,
        data_freshness,
        observation_mode,
        freshness,
        len(stellarium_data) > 0,
        priority_object,
    )

    if include_external:
        try:
            nasa_data = get_nasa_apod()
        except Exception:
            nasa_data = {}
        if not isinstance(nasa_data, dict):
            nasa_data = {}
    else:
        nasa_data = {}
    tle_risk = compute_tle_risk_signal(data_freshness)
    final_core = build_final_core(priority_object, tle_risk, nasa_data)

    _metrics = metrics_status_fields()
    return {
        "status": status,
        "tle": tle_ui,
        "tle_count": tle_n,
        "images": images,
        "mode": mode,
        "uptime_seconds": uptime_seconds,
        "last_update": last_update,
        "passes_predicted": 0,
        "observer": STATUS_OBSERVER_LABEL,
        "data_freshness": data_freshness,
        "production_mode": production_mode,
        "tle_backend_status": tle_raw,
        "system_status": status,
        "system": {
            "status": status,
            "tle_status": tle_raw,
            "last_update": last_update,
            "mode": production_mode,
        },
        "errors_last_5min": _metrics["errors_last_5min"],
        "requests_per_min": _metrics["requests_per_min"],
        "stellarium": {
            "objects_detected": len(stellarium_data),
            "active": len(stellarium_data) > 0,
            "last_object": last_object,
            "last_timestamp": last_timestamp,
            "freshness": freshness,
        },
        "observation_mode": observation_mode,
        "priority_object": priority_object,
        "system_intelligence": system_intelligence,
        "nasa": {
            "title": nasa_data.get("title"),
            "date": nasa_data.get("date"),
            "image": nasa_data.get("url"),
        },
        "tle_signal": {
            "risk": tle_risk,
            "freshness": data_freshness,
        },
        "final_core": final_core,
    }


def get_status_data():
    """Même contenu logique que GET /status (dict), pour self-test / validation."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        return _build_status_payload_dict(now_iso)
    except Exception as ex:
        log.warning("get_status_data: %s", ex)
        try:
            struct_log(
                logging.ERROR,
                category="validation",
                event="status_assemble_failed",
                error=str(ex)[:400],
            )
        except Exception:
            pass
        return _fallback_status_payload_dict(now_iso)


def validate_system_state(status):
    """Contrôle structurel minimal avant mise en prod (clés fusion / TLE / NASA)."""
    errors = []
    try:
        st = status if isinstance(status, dict) else {}
        if not st.get("system_status"):
            errors.append("missing system_status")
        if "tle" not in st:
            errors.append("missing tle")
        if "nasa" not in st:
            errors.append("missing nasa")
        if "final_core" not in st:
            errors.append("missing final_core")
    except Exception as ex:
        errors.append("validation_exception: %s" % ex)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


# ── Lightweight status for UI/showroom monitoring ────────────────────────────
def build_status_snapshot_dict():
    """
    Même charge utile que GET /status (dict + performance.response_time_ms).
    Source unique pour HTTP, WebSocket et tests — évite la divergence client/serveur.
    """
    start_time = time.time()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        payload = _build_status_payload_dict(now_iso)
        payload["performance"] = {"response_time_ms": int((time.time() - start_time) * 1000)}
        return payload
    except Exception as e:
        try:
            _health_set_error("status_endpoint", e, "critical")
        except Exception:
            pass
        try:
            struct_log(
                logging.ERROR,
                category="api",
                event="status_endpoint_exception",
                error=str(e)[:400],
            )
        except Exception:
            pass
        payload = _fallback_status_payload_dict(now_iso)
        payload["performance"] = {"response_time_ms": 0}
        return payload


try:
    from flask_sock import Sock

    _sock = Sock(app)

    @_sock.route("/ws/status")
    def ws_status(ws):
        """
        WebSocket optionnel : pousse le même JSON que /status toutes les ~3 s.
        Avec Gunicorn, préférer un worker compatible WebSocket (ex. gevent) si ce flux est utilisé en prod.
        """
        while True:
            try:
                payload = build_status_snapshot_dict()
                ws.send(json.dumps(payload, default=str))
            except Exception:
                break
            time.sleep(3)

    @_sock.route("/ws/view-sync")
    def ws_view_sync(ws):
        """
        Synchronisation de vue — view_sync_backend.py.
        Query : sessionId, viewRole, sourceDevice, sessionKey (si VIEW_SYNC_SESSION_KEY défini).
        """
        from flask import request

        from view_sync_backend import (
            VIEW_SYNC_MAX_BYTES,
            get_expected_session_key,
            get_view_sync_hub,
        )

        exp_key = get_expected_session_key()
        if exp_key:
            qk = (request.args.get("sessionKey") or "").encode("utf-8")
            xk = exp_key.encode("utf-8")
            try:
                ok = secrets.compare_digest(qk, xk)
            except Exception:
                ok = False
            if not ok:
                try:
                    ws.close()
                except Exception:
                    pass
                return

        sid = (request.args.get("sessionId") or "orbital-chohra-main").strip()[:128] or "orbital-chohra-main"
        vr = (request.args.get("viewRole") or "master").strip().lower()[:32]
        if vr not in ("master", "viewer", "collaborative"):
            vr = "master"
        sdev = (request.args.get("sourceDevice") or "").strip()[:256]
        hub = get_view_sync_hub()
        hub.client_connected(ws, sid, view_role=vr, source_device=sdev)
        try:
            while True:
                try:
                    raw = ws.receive()
                except Exception:
                    break
                if raw is None:
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                if not isinstance(raw, str) or len(raw) > VIEW_SYNC_MAX_BYTES:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                mtype = obj.get("type")
                if mtype == "VIEW_STATE":
                    hub.on_client_message(ws, sid, raw, obj)
                elif mtype == "HEARTBEAT":
                    hub.on_heartbeat(ws, sid, obj)
                elif mtype == "REQUEST_MASTER":
                    hub.on_request_master(ws, sid, obj)
        finally:
            hub.client_disconnected(ws, sid)
except ImportError:
    pass


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

# MIGRATED TO telescope_bp PASS 9 — /telescopes → see app/blueprints/telescope/__init__.py (telescopes_page)


def _fetch_hubble():
    NASA_KEY = (os.environ.get('NASA_API_KEY') or 'DEMO_KEY').strip()

    # Source 1 : NASA APOD avec images Hubble réelles
    raw = _curl_get(f'https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}&count=6', timeout=10)
    if raw:
        try:
            items = json.loads(raw)
            imgs = []
            for i in items:
                if i.get('url') and i.get('media_type', 'image') == 'image':
                    imgs.append({
                        'title': i.get('title', 'Hubble'),
                        'url': i.get('hdurl') or i.get('url', ''),
                        'date': i.get('date', '')
                    })
            if imgs:
                return imgs
        except Exception:
            pass

    # Source 2 : Titres Hubble fixes en français (APOD/Webb)
    return [
        {'title': 'Piliers de la Création', 'url': 'https://apod.nasa.gov/apod/image/2304/M16Pillar_Webb_960.jpg'},
        {'title': 'Galaxie du Tourbillon M51', 'url': 'https://apod.nasa.gov/apod/image/2305/M51_HubbleWebb_960.jpg'},
        {'title': 'Nébuleuse de la Carène', 'url': 'https://apod.nasa.gov/apod/image/2207/Carina_Webb_960.jpg'},
        {'title': 'Quintette de Stephan', 'url': 'https://apod.nasa.gov/apod/image/2207/StephansQuintet_Webb_1024.jpg'},
        {'title': "Galaxie d'Andromède M31", 'url': 'https://apod.nasa.gov/apod/image/0601/m31_ware_960.jpg'},
        {'title': "Grande Nébuleuse d'Orion M42", 'url': 'https://apod.nasa.gov/apod/image/2301/M42_Webb_960.jpg'}
    ]



# MIGRATED TO telescope_bp PASS 9 — /api/hubble/images → see app/blueprints/telescope/__init__.py (api_hubble_images)


# MIGRATED TO feeds_bp PASS 8 — /api/mars/weather → see app/blueprints/feeds/__init__.py (api_mars_weather)


# MIGRATED TO feeds_bp PASS 15 — /api/bepi/telemetry → see app/blueprints/feeds/__init__.py (api_bepi)


# MIGRATED TO ai_bp PASS 10 — /api/jwst/images → see app/blueprints/ai/__init__.py (api_jwst_images)
# MIGRATED TO ai_bp PASS 10 — /api/jwst/refresh → see app/blueprints/ai/__init__.py (api_jwst_refresh)
# (différés PASS 8/9 levés : helpers _fetch_jwst_live_images + _JWST_STATIC déplacés vers
#  app/services/observatory_feeds.py)


# MIGRATED TO feeds_bp PASS 8 — /api/neo → see app/blueprints/feeds/__init__.py (api_neo)
# MIGRATED TO feeds_bp PASS 8 — /api/nasa/apod → see app/blueprints/feeds/__init__.py (api_nasa_apod)





# MIGRATED TO feeds_bp PASS 8 — /api/nasa/neo → see app/blueprints/feeds/__init__.py (api_nasa_neo)
# MIGRATED TO feeds_bp PASS 8 — /api/nasa/solar → see app/blueprints/feeds/__init__.py (api_nasa_solar)
# MIGRATED TO feeds_bp PASS 8 — /api/alerts/asteroids → see app/blueprints/feeds/__init__.py (api_asteroids)
# MIGRATED TO feeds_bp PASS 8 — /api/alerts/solar → see app/blueprints/feeds/__init__.py (api_solar)
# MIGRATED TO feeds_bp PASS 8 — /api/alerts/all → see app/blueprints/feeds/__init__.py (api_alerts_all)
# MIGRATED TO feeds_bp PASS 8 — /api/live/spacex → see app/blueprints/feeds/__init__.py (api_spacex)


_NEWS_TRADUCTIONS = {
    'launches': 'lancements',
    'satellite': 'satellite',
    'mission': 'mission',
    'rocket': 'fusée',
    'space': 'espace',
    'NASA': 'NASA',
    'SpaceX': 'SpaceX',
}


def _apply_news_translations(items):
    """Remplace quelques termes fréquents dans titres/résumés des news (ordre pour éviter space→SpaceX)."""
    if not items:
        return items
    order = ['SpaceX', 'NASA', 'launches', 'satellite', 'mission', 'rocket', 'space']
    tr = _NEWS_TRADUCTIONS
    out = []
    for a in items:
        title = a.get('title', '')
        summary = a.get('summary', '')
        for en in order:
            if en in tr:
                title = title.replace(en, tr[en])
                summary = summary.replace(en, tr[en])
        out.append({**a, 'title': title, 'summary': summary})
    return out


# MIGRATED TO feeds_bp PASS 8 — /api/live/news → see app/blueprints/feeds/__init__.py (api_space_news)
# MIGRATED TO feeds_bp PASS 8 — /api/live/mars-weather → see app/blueprints/feeds/__init__.py (api_live_mars_weather)
# MIGRATED TO feeds_bp PASS 8 — /api/live/iss-passes → see app/blueprints/feeds/__init__.py (api_live_iss_passes)




# MIGRATED TO iss_bp PASS 14 — /api/iss/ground-track → see app/blueprints/iss/routes.py (api_iss_ground_track)


# MIGRATED TO iss_bp PASS 11 — /api/iss/orbit → see app/blueprints/iss/routes.py (api_iss_orbit)


# MIGRATED TO iss_bp PASS 11 — /api/iss/crew → see app/blueprints/iss/routes.py (api_iss_crew)


# MIGRATED TO iss_bp PASS 14 — /api/iss/passes → see app/blueprints/iss/routes.py (api_iss_passes_tlemcen)
# MIGRATED TO iss_bp PASS 14 — /api/iss/passes/<float:lat>/<float:lon> → see app/blueprints/iss/routes.py (api_iss_passes_observer)


def _fetch_swpc_alerts():
    """Alertes NOAA SWPC dernières 24h — format normalisé."""
    import datetime as _dt
    try:
        raw = _curl_get('https://services.swpc.noaa.gov/products/alerts.json', timeout=12)
        if not raw:
            return []
        data = _safe_json_loads(raw, 'swpc_alerts')
        if not isinstance(data, list):
            return []
        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24)
        alerts = []
        for item in data:
            if not isinstance(item, dict):
                continue
            issued_str = (item.get('issue_datetime') or item.get('issued') or '').strip()
            try:
                issued_dt = _dt.datetime.strptime(issued_str[:16], '%Y-%m-%d %H:%M')
            except Exception:
                try:
                    issued_dt = _dt.datetime.strptime(issued_str[:16], '%Y-%m-%dT%H:%M')
                except Exception:
                    issued_dt = _dt.datetime.now(_dt.timezone.utc)
            if issued_dt < cutoff:
                continue
            msg = (item.get('message') or item.get('msg') or '').strip()
            # Detect type and level from message
            alert_type = 'Alerte Spatiale'
            level = ''
            msg_up = msg.upper()
            if 'GEOMAGNETIC' in msg_up or 'K-INDEX' in msg_up or 'G-SCALE' in msg_up:
                alert_type = 'Tempête Géomagnétique'
                for g in ['G5', 'G4', 'G3', 'G2', 'G1']:
                    if g in msg_up:
                        level = g
                        break
                if not level:
                    import re as _re
                    m_k = _re.search(r'K-?index\s+of\s+(\d)', msg, _re.IGNORECASE)
                    if m_k:
                        k = int(m_k.group(1))
                        level = 'G' + str(max(1, min(5, k - 4))) if k >= 5 else 'Kp=' + str(k)
            elif 'SOLAR FLARE' in msg_up or 'X-RAY' in msg_up or 'FLARE' in msg_up:
                alert_type = 'Éruption Solaire'
                import re as _re
                m_f = _re.search(r'\b([XMC]\d[\.\d]*)\b', msg, _re.IGNORECASE)
                if m_f:
                    level = m_f.group(1).upper()
                else:
                    for cls in ['X', 'M', 'C']:
                        if cls + '-CLASS' in msg_up or ' ' + cls + ' CLASS' in msg_up:
                            level = cls
                            break
            elif 'RADIATION STORM' in msg_up or 'S-SCALE' in msg_up or 'PROTON' in msg_up:
                alert_type = 'Tempête Radiative'
                for s in ['S5', 'S4', 'S3', 'S2', 'S1']:
                    if s in msg_up:
                        level = s
                        break
            elif 'RADIO BLACKOUT' in msg_up or 'R-SCALE' in msg_up:
                alert_type = 'Éclipse Radio'
                for r in ['R5', 'R4', 'R3', 'R2', 'R1']:
                    if r in msg_up:
                        level = r
                        break
            alerts.append({
                'type': alert_type,
                'level': level,
                'message': msg[:300],
                'issued': issued_str,
                'issued_dt': issued_dt.strftime('%Y-%m-%dT%H:%M'),
            })
        return sorted(alerts, key=lambda x: x['issued_dt'], reverse=True)[:10]
    except Exception as e:
        log.warning('swpc_alerts: %s', e)
        return []


# MIGRATED TO feeds_bp PASS 8 — /api/space-weather/alerts → see app/blueprints/feeds/__init__.py (api_space_weather_alerts)
# MIGRATED TO feeds_bp PASS 8 — /api/live/all → see app/blueprints/feeds/__init__.py (api_live_all)


# MIGRATED TO iss_bp PASS 11 — /api/iss-passes → see app/blueprints/iss/routes.py (api_iss_passes_n2yo)


# MIGRATED TO system_bp PASS 11 — /api/dsn → see app/blueprints/system/__init__.py (api_dsn)












# MIGRATED TO pages_bp PASS 11 — /globe → see app/blueprints/pages/__init__.py (globe)


# MIGRATED TO feeds_bp PASS 14 — /api/survol → see app/blueprints/feeds/__init__.py (api_survol)


# ══════════════════════════════════════════════════════════════
# DIGITAL LAB — Image analysis pipeline (new module)
# ══════════════════════════════════════════════════════════════
# PASS 20.3 (2026-05-08) — Lab/Skyview helpers extracted to app/services/lab_helpers.py
# Shim re-exports for backward compatibility (lab_bp + research_bp utilisent
# `from station_web import LAB_UPLOADS` etc. via lazy imports).
from app.services.lab_helpers import (  # noqa: E402,F401
    _lab_last_report,
    LAB_UPLOADS,
    MAX_LAB_IMAGE_BYTES,
    RAW_IMAGES,
    ANALYSED_IMAGES,
    SPACE_IMAGE_DB,
    METADATA_DB,
    _sync_skyview_to_lab,
)
# LAB_LOGS_DIR + makedirs side-effects + SKYVIEW_DIR conservés ici (init disque
# au load du monolith ; non extraits car ne font pas partie du périmètre PASS 20.3).
LAB_LOGS_DIR = os.path.join(STATION, "data", "images_espace", "logs")
os.makedirs(RAW_IMAGES, exist_ok=True)
os.makedirs(ANALYSED_IMAGES, exist_ok=True)
os.makedirs(METADATA_DB, exist_ok=True)
os.makedirs(LAB_LOGS_DIR, exist_ok=True)
# Dossier SkyView — captures alimentent le lab via _sync_skyview_to_lab()
SKYVIEW_DIR = os.path.join(STATION, "data", "skyview")
os.makedirs(SKYVIEW_DIR, exist_ok=True)


# PASS 27.10 (2026-05-09) — Image downloads helpers (6 fonctions ~201 lignes
# corps) déplacés vers source de vérité unique app/services/image_downloads.py
# (nouveau module créé en PASS 27.10).
# Re-exporté ici pour préserver le lazy import de app/workers/lab_image_collector.py
# (`from station_web import _download_nasa_apod, _download_hubble_images,
# _download_jwst_images, _download_esa_images, ...` — pattern PASS 21.4 cycle-safe).
from app.services.image_downloads import (  # noqa: F401 (re-export)
    log_rejected_image,
    save_normalized_metadata,
    _download_nasa_apod,
    _download_hubble_images,
    _download_jwst_images,
    _download_esa_images,
)


# MIGRATED TO lab_bp PASS 13 — /lab → see app/blueprints/lab/__init__.py (digital_lab)
# MIGRATED TO lab_bp PASS 13 — /lab/upload POST → see app/blueprints/lab/__init__.py (lab_upload)
# MIGRATED TO lab_bp PASS 13 — /lab/images → see app/blueprints/lab/__init__.py (lab_images)
# MIGRATED TO lab_bp PASS 13 — /api/lab/images → see app/blueprints/lab/__init__.py (api_lab_images)
# MIGRATED TO lab_bp PASS 13 — /lab/raw/<path:filename> → see app/blueprints/lab/__init__.py (lab_raw_file)
# MIGRATED TO lab_bp PASS 13 — /api/lab/metadata/<path:filename> → see app/blueprints/lab/__init__.py (api_lab_metadata)
# MIGRATED TO lab_bp PASS 13 — /lab/analyze POST → see app/blueprints/lab/__init__.py (lab_analyze)
# MIGRATED TO lab_bp PASS 13 — /lab/dashboard → see app/blueprints/lab/__init__.py (lab_dashboard)
# MIGRATED TO lab_bp PASS 13 — /api/lab/run_analysis POST → see app/blueprints/lab/__init__.py (api_lab_run_analysis)
# MIGRATED TO lab_bp PASS 13 — /api/lab/skyview/sync → see app/blueprints/lab/__init__.py (force_skyview_sync)


# PASS 27.10 (2026-05-09) — _download_nasa_apod / _download_hubble_images /
# _download_jwst_images / _download_esa_images déplacés vers
# app/services/image_downloads.py (re-exportés via le bloc d'import plus haut).


# PASS 20.3 (2026-05-08) — _sync_skyview_to_lab() extrait vers
# app/services/lab_helpers.py. Le nom est ré-importé via le shim de section
# DIGITAL LAB ci-dessus. Les usages internes (e.g. _start_skyview_sync below)
# continuent de fonctionner via la liaison du shim au namespace de ce module.


# PASS 21.3 (2026-05-08) — Skyview sync thread extracted to app/workers/skyview_sync.py
# Shim re-export for backward compatibility (app/bootstrap.py:52 imports
# `from station_web import _start_skyview_sync` to start the thread.)
# La fonction _sync_skyview_to_lab() consommée par la boucle est
# fournie par app/services/lab_helpers.py (PASS 20.3).
from app.workers.skyview_sync import _start_skyview_sync  # noqa: E402,F401


# PASS 21.4 (2026-05-08) — Lab image collector thread (LAST thread) extracted
# to app/workers/lab_image_collector.py. Avec ce PASS, les 4 threads sont
# tous dans app/workers/ — plus aucun thread dans station_web.py.
#
# Symboles déplacés vers le worker (~108 lignes) :
#   - 3 constantes : LOCK_FILE, LAST_RUN_FILE, COOLDOWN_SECONDS
#   - 7 fonctions : _aegis_collector_acquire_lock, _aegis_collector_release_lock,
#     _aegis_collector_can_run, _aegis_collector_mark_run, run_collector_safe,
#     _run_lab_image_collector_once, _start_lab_image_collector
#
# Audit a confirmé un seul consommateur externe : app/bootstrap.py:44
# fait `from station_web import _start_lab_image_collector`. Les 9 autres
# symboles sont internes au worker (pas de re-export nécessaire).
#
# Pattern leader/standby fcntl.flock préservé : LOCK_EX|LOCK_NB exclusif
# entre les 4 workers Gunicorn ; LAST_RUN_FILE pour cooldown 60s.
# Mutation cross-module : _aegis_collector_mark_run mute
# station_web.COLLECTOR_LAST_RUN via `import station_web as _sw` pour
# rétro-compat défensive (audit confirme aucun lecteur actif externe).
#
# Path globals (RAW_IMAGES, METADATA_DB) fournis par app/services/lab_helpers.py
# (PASS 20.3) via lazy imports inside _run_lab_image_collector_once.
from app.workers.lab_image_collector import _start_lab_image_collector  # noqa: E402,F401


# PASS 21.1 (2026-05-08) — translate_worker extracted to app/workers/translate_worker.py
# Shim re-export for backward compatibility (app/bootstrap.py:60 imports
# `from station_web import translate_worker` to start the thread.)
# Le corps original (49 lignes) a été déplacé verbatim vers le worker
# avec lazy imports inside pour DB_PATH/log (cycle-safe au load).
from app.workers.translate_worker import translate_worker  # noqa: E402,F401


# ══════════════════════════════════════════════════════════════
# Catalogue TLE complet (Celestrak) — data/tle/, /api/tle/full
# ══════════════════════════════════════════════════════════════
# PASS 2D Cat 2 (2026-05-07) : TLE_DIR + TLE_ACTIVE_PATH retirés ici, désormais
# définis dans app/services/tle.py et re-exportés en haut de ce fichier.

# PASS 20.2 (2026-05-08) — TLE/Satellites helpers extracted to app/services/tle_cache.py
# Shim re-exports for backward compatibility (les blueprints satellites_bp,
# iss_bp, api_bp importent encore via `from station_web import TLE_CACHE` etc.)
from app.services.tle_cache import (  # noqa: E402,F401
    _parse_tle_file,
    list_satellites,
    TLE_CACHE,
    TLE_ACTIVE_PATH,
    TLE_MAX_SATELLITES,
)


# PASS 21.2 (2026-05-08) — TLE collector thread extracted to app/workers/tle_collector.py
# Shim re-exports for backward compatibility (app/bootstrap.py:70 imports
# `from station_web import _start_tle_collector` to start the thread.)
# Les 5 fonctions (~185 lignes corps) ont été déplacées verbatim avec
# lazy imports inside pour TLE_CACHE/TLE_ACTIVE_PATH/_parse_tle_file
# (depuis app.services.tle_cache PASS 20.2) et HEALTH_STATE/log
# (depuis station_web — cycle-safe).
from app.workers.tle_collector import (  # noqa: E402,F401
    download_tle_now,
    refresh_tle_from_amsat,
    _download_tle_catalog,
    _run_tle_download_once,
    _start_tle_collector,
)


# PASS 21.2 (2026-05-08) — refresh_tle_from_amsat, _download_tle_catalog,
# _run_tle_download_once, _start_tle_collector déplacés vers
# app/workers/tle_collector.py (ré-importés via le shim plus haut).
# PASS 2D Cat 2 (2026-05-07) : _parse_tle_file extrait → app/services/tle.py
# (re-export en haut de ce fichier).

# MIGRATED TO satellites_bp PASS 14 — /api/satellites/tle → see app/blueprints/satellites/__init__.py (api_satellites_tle)
# MIGRATED TO satellites_bp PASS 14 — /api/satellites/tle/debug → see app/blueprints/satellites/__init__.py (debug_tle)


try:
    refresh_tle_from_amsat()
except Exception:
    try:
        print("TLE skipped — offline mode")
    except Exception:
        pass
if os.path.isfile(TLE_ACTIVE_PATH):
    log.info("TLE FILE SIZE: %s", os.path.getsize(TLE_ACTIVE_PATH))
else:
    log.warning("TLE active.tle missing after startup")


# PASS 2D Cat 2 (2026-05-07) : _TLE_FOR_PASSES extrait → app/services/tle.py
# (re-export en haut de ce fichier).


def _elevation_above_observer(lat, lon, jd, fr, obs_teme, obs_norm, sat_teme):
    """Élévation (degrés) du satellite vu depuis l'observateur (TEME, km)."""
    import math
    dx = sat_teme[0] - obs_teme[0]
    dy = sat_teme[1] - obs_teme[1]
    dz = sat_teme[2] - obs_teme[2]
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist < 1e-6:
        return -90.0
    ux, uy, uz = dx / dist, dy / dist, dz / dist
    dot = ux * (obs_teme[0] / obs_norm) + uy * (obs_teme[1] / obs_norm) + uz * (obs_teme[2] / obs_norm)
    return math.degrees(math.asin(max(-1, min(1, dot))))


# MIGRATED TO satellites_bp PASS 14 — /api/satellite/passes → see app/blueprints/satellites/__init__.py (api_satellite_passes)


# MIGRATED TO pages_bp PASS 5 — /research → see app/blueprints/pages/__init__.py (research)
# MIGRATED TO pages_bp PASS 5 — /space → see app/blueprints/pages/__init__.py (space)
# MIGRATED TO pages_bp PASS 5 — /space-intelligence → see app/blueprints/pages/__init__.py (space_intelligence)
# MIGRATED TO pages_bp PASS 5 — /module/<name> → see app/blueprints/pages/__init__.py (module)

# MIGRATED TO lab_bp PASS 13 — /api/lab/upload POST → see app/blueprints/lab/__init__.py (api_lab_upload)
# MIGRATED TO lab_bp PASS 13 — /api/lab/analyze POST → see app/blueprints/lab/__init__.py (api_lab_analyze)
# MIGRATED TO lab_bp PASS 13 — /api/lab/report → see app/blueprints/lab/__init__.py (api_lab_report)
# MIGRATED TO lab_bp PASS 13 — /api/analysis/run POST → see app/blueprints/lab/__init__.py (api_analysis_run)
# MIGRATED TO lab_bp PASS 13 — /api/analysis/compare POST → see app/blueprints/lab/__init__.py (api_analysis_compare)
# MIGRATED TO lab_bp PASS 13 — /api/analysis/discoveries → see app/blueprints/lab/__init__.py (api_analysis_discoveries)
# MIGRATED TO research_bp PASS 13 — /research-center → see app/blueprints/research/__init__.py (research_center_page)
# MIGRATED TO research_bp PASS 13 — /api/research/summary → see app/blueprints/research/__init__.py (api_research_summary)
# MIGRATED TO research_bp PASS 13 — /api/research/events → see app/blueprints/research/__init__.py (api_research_events)
# MIGRATED TO research_bp PASS 13 — /api/research/logs → see app/blueprints/research/__init__.py (api_research_logs)


# ══════════════════════════════════════════════════════════════
# SCIENCE ARCHIVE — Automatic archive for scientific outputs (new)
# Receives results from Digital Lab / Space Analysis via API; does not modify existing modules
# ══════════════════════════════════════════════════════════════
# MIGRATED TO archive_bp PASS 6 — /api/archive/reports → see app/blueprints/archive/__init__.py (api_archive_reports)
# MIGRATED TO archive_bp PASS 6 — /api/archive/objects → see app/blueprints/archive/__init__.py (api_archive_objects)
# MIGRATED TO archive_bp PASS 6 — /api/archive/discoveries → see app/blueprints/archive/__init__.py (api_archive_discoveries)


# ══════════════════════════════════════════════════════════════
# Carte orbitale mondiale — positions satellites live
# ══════════════════════════════════════════════════════════════


# MIGRATED TO pages_bp PASS 5 — /demo → see app/blueprints/pages/__init__.py (astroscan_demo_page)


# MIGRATED TO feeds_bp PASS 11 — /api/orbits/live → see app/blueprints/feeds/__init__.py (api_orbits_live)


# ══════════════════════════════════════════════════════════════
# Météo spatiale
# ══════════════════════════════════════════════════════════════

# MIGRATED TO weather_bp PASS 7 — /api/space-weather → see app/blueprints/weather/__init__.py (api_space_weather)
# MIGRATED TO weather_bp PASS 7 — /space-weather → see app/blueprints/weather/__init__.py (space_weather_page)


# ══════════════════════════════════════════════════════════════
# Analyse scientifique d'images
# ══════════════════════════════════════════════════════════════

# MIGRATED TO research_bp PASS 13 — /api/science/analyze-image POST → see app/blueprints/research/__init__.py (api_science_analyze_image)


# ══════════════════════════════════════════════════════════════
# Mission Control — vue consolidée
# ══════════════════════════════════════════════════════════════

# MIGRATED TO feeds_bp PASS 11 — /api/missions/overview → see app/blueprints/feeds/__init__.py (api_missions_overview)


# ══════════════════════════════════════════════════════════════
# Intelligence spatiale
# ══════════════════════════════════════════════════════════════

# MIGRATED TO research_bp PASS 13 — /api/space/intelligence GET+POST → see app/blueprints/research/__init__.py (api_space_intelligence)


# MIGRATED TO pages_bp PASS 5 — /space-intelligence-page → see app/blueprints/pages/__init__.py (space_intelligence_page)






# MIGRATED TO main_bp PASS 5 — /favicon.ico → see app/blueprints/main/__init__.py (favicon)



# ═══ TÉLESCOPE NASA SKYVIEW ═══════════════════════════════════
# PASS 19 cleanup : import skyview retiré (telescope_bp importe en direct).

# MIGRATED TO telescope_bp PASS 9 — /telescope → see app/blueprints/telescope/__init__.py (telescope)
# MIGRATED TO telescope_bp PASS 9 — /api/telescope/image → see app/blueprints/telescope/__init__.py (api_telescope_image)
# MIGRATED TO telescope_bp PASS 9 — /api/telescope/catalogue → see app/blueprints/telescope/__init__.py (api_telescope_catalogue)
# MIGRATED TO telescope_bp PASS 9 — /api/telescope/proxy-image → see app/blueprints/telescope/__init__.py (api_telescope_proxy_image)


# MIGRATED TO pages_bp PASS 5 — /aladin + /carte-du-ciel → see app/blueprints/pages/__init__.py (aladin_page)


# Prêt à recevoir du trafic : import Gunicorn/worker terminé (TLE + routes chargés).
server_ready = True



# MIGRATED TO iss_bp PASS 11 — /api/iss/stream → see app/blueprints/iss/routes.py (iss_stream)

# MIGRATED TO telescope_bp PASS 9 — /api/telescope/stream → see app/blueprints/telescope/__init__.py (telescope_stream)
# MIGRATED TO telescope_bp PASS 9 — /api/telescope/status → see app/blueprints/telescope/__init__.py (telescope_status)
# MIGRATED TO telescope_bp PASS 9 — /api/stellarium → see app/blueprints/telescope/__init__.py (api_stellarium)



# ══════════════════════════════════════════════════════════════
# OWNER IPs — gestion des IPs propriétaire via API
# ══════════════════════════════════════════════════════════════



# MIGRATED TO analytics_bp PASS 12 — /api/owner-ips POST → see app/blueprints/analytics/__init__.py (api_owner_ips_add)
# MIGRATED TO analytics_bp PASS 12 — /api/owner-ips/<int:ip_id> DELETE → see app/blueprints/analytics/__init__.py (api_owner_ips_delete)
# MIGRATED TO analytics_bp PASS 12 — /api/visitor/score-update POST → see app/blueprints/analytics/__init__.py (api_visitor_score_update)
# MIGRATED TO analytics_bp PASS 12 — /api/analytics/summary → see app/blueprints/analytics/__init__.py (api_analytics_summary)



# ── GEO-IP TRACKER ───────────────────────────────────────
# PASS 23 — moved to app/services/db_visitors.py
from app.services.db_visitors import _get_db_visitors  # noqa: F401 (re-export)


# MIGRATED TO analytics_bp PASS 12 — /api/visitors/globe-data → see app/blueprints/analytics/__init__.py (api_visitors_globe_data)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/stream → see app/blueprints/analytics/__init__.py (api_visitors_stream)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/log POST → see app/blueprints/analytics/__init__.py (api_log_visitor)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/geo → see app/blueprints/analytics/__init__.py (api_visitors_geo)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/stats → see app/blueprints/analytics/__init__.py (api_visitors_stats)

# MIGRATED TO analytics_bp PASS 16 — /api/visitors/connection_time → see app/blueprints/analytics/__init__.py (api_visitors_connection_time)


# ── Temps passé par page (session_time) — script injecté dans HTML, endpoint dédié ──
_SESSION_TIME_SNIPPET = (
    '<!-- astroscan-session-time --><script>'
    '(function(){var t0=Date.now(),sent=!1;'
    "function getSid(){var c=document.cookie.split(';');for(var i=0;i<c.length;i++){"
    "var p=c[i].trim();if(p.indexOf('astroscan_sid=')===0)return decodeURIComponent(p.slice(14));}"
    "return '';}function send(){if(sent)return;sent=!0;var d=Math.max(0,Math.round((Date.now()-t0)/1000)),"
    "body=JSON.stringify({session_id:getSid(),path:window.location.pathname||'/',duration:d});"
    "try{if(navigator.sendBeacon){var b=new Blob([body],{type:'application/json'});"
    "if(navigator.sendBeacon('/track-time',b))return;}}catch(e){}"
    "try{fetch('/track-time',{method:'POST',headers:{'Content-Type':'application/json'},body:body,keepalive:!0});}catch(e){}}"
    "window.addEventListener('pagehide',send);window.addEventListener('beforeunload',send);})();"
    "</script>"
)


# MIGRATED TO analytics_bp PASS 12 — /track-time POST → see app/blueprints/analytics/__init__.py (track_time_endpoint)


# PASS 26.2 (2026-05-08) — @app.after_request _astroscan_session_cookie_and_time_script supprimé.
# Source de vérité : app/hooks.py (registered via app/__init__.py:_register_hooks
# et station_web.py PASS 25.5 fallback safety).


# ══════════════════════════════════════════════════════════════
# MODULE HILAL — Croissant Islamique · Tlemcen 34.87°N 1.32°E
# ══════════════════════════════════════════════════════════════



# MIGRATED TO astro_bp PASS 15 — /api/hilal/calendar → see app/blueprints/astro/__init__.py (api_hilal_calendar)
# MIGRATED TO astro_bp PASS 15 — /api/hilal → see app/blueprints/astro/__init__.py (api_hilal)
# Helpers _hilal_compute, _hilal_compute_calendar, _HIJRI_MONTHS extraits → app/services/hilal_compute.py



# MIGRATED TO weather_bp PASS 7 — /api/meteo/reel → see app/blueprints/weather/__init__.py (meteo_reel)
# MIGRATED TO weather_bp PASS 7 — /meteo-reel → see app/blueprints/weather/__init__.py (meteo_page)
# MIGRATED TO weather_bp PASS 7 — /control + /meteo → see app/blueprints/weather/__init__.py (control)


# MIGRATED TO astro_bp PASS 7 — /ephemerides + helper _compute_ephemerides_tlemcen_astropy → see app/blueprints/astro/__init__.py (page_ephemerides)


# MIGRATED TO seo_bp PASS 5 — /sitemap.xml DOUBLON (déjà dans seo_bp/routes.py — version BP plus complète conservée)
# MIGRATED TO seo_bp PASS 5 — /robots.txt DOUBLON (déjà dans seo_bp/routes.py — version BP plus complète conservée)
# MIGRATED TO pages_bp PASS 5 — /europe-live → see app/blueprints/pages/__init__.py (europe_live)
# MIGRATED TO pages_bp PASS 5 — /flight-radar → see app/blueprints/pages/__init__.py (flight_radar)


# ── PROXY CAMÉRAS — World Live ────────────────────────────────────────────────
# Caméras publiques mondiales, choisies pour stabilité et impact visuel.
# '__epic__' est une sentinelle : résout dynamiquement la dernière image NASA EPIC.
# MIGRATED TO cameras_bp PASS 15 — /proxy-cam/<city>.jpg → see app/blueprints/cameras/__init__.py (proxy_cam)
# Helpers _CAM_*, _cam_resolve, _cam_fetch_url, _cam_response, _get_latest_epic_url copiés dans cameras_bp


# MIGRATED TO main_bp PASS 14 — /contact POST → see app/blueprints/main/__init__.py (contact_form)
# MIGRATED TO feeds_bp PASS 14 — /api/flights → see app/blueprints/feeds/__init__.py (api_flights)


# ══════════════════════════════════════════════════════════════
# PASS 25.5 — FALLBACK SAFETY (Strangler Fig Pattern Restoration)
# ══════════════════════════════════════════════════════════════
# Restauration du filet de sécurité retiré par PASS 25.3 (commit 4cebf53).
# wsgi.py documente un fallback automatique : si create_app() échoue
# au boot, le service retombe sur station_web.app. Ce bloc garantit
# que station_web.app a bien tous les BPs/hooks registered pour servir
# l'application en mode dégradé.
#
# Single source of truth : app/__init__.py:_register_blueprints + _register_hooks
# (synchronisation automatique en cas d'ajout/retrait de BPs).
#
# Coût mémoire : ~5-10 MB par worker (29 BPs × 2 instances Flask).
# Coût démarrage : +50-150 ms par worker.
# Bénéfice : rollback instantané via ASTROSCAN_FORCE_MONOLITH=1.
try:
    from app import register_all_for_fallback
    register_all_for_fallback(app)
except Exception as _fallback_exc:
    log.warning(
        "[fallback-safety] station_web.app cannot register BPs: %s "
        "(ASTROSCAN_FORCE_MONOLITH=1 will serve a degraded site)",
        _fallback_exc,
    )


if __name__ == '__main__':
    os.makedirs(f'{STATION}/logs', exist_ok=True)
    os.makedirs(f'{STATION}/data', exist_ok=True)
    os.makedirs(f'{STATION}/telescope_live', exist_ok=True)
    _init_visits_table()  # Table compteur visites
    log.info("═══ ORBITAL-CHOHRA STATION WEB — DÉMARRAGE ═══")
    import socket
    def _find_port(start=5000, count=20):
        """Évite 80/443 (souvent nginx) — cherche un port libre dans la plage."""
        for p in range(start, start + count):
            if p in (80, 443):
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', p))
                s.close()
                return p
            except OSError:
                continue
        log.warning("Aucun port libre dans la plage — tentative port %s", start)
        return start
    port = 5003
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
