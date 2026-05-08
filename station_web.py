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
_REQ_DEFAULT_TIMEOUT = 10
_REQ_SLOW_MS = 1500
_REQ_VERY_SLOW_MS = 5000
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
MAX_CACHE_SIZE = 500


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
CLAUDE_MAX_CALLS = 100
CLAUDE_80_WARNING_SENT = False
GROQ_CALL_COUNT = 0
COLLECTOR_LAST_RUN = 0

# ── Config ──────────────────────────────────────────────────
# PASS 23 — moved to app/services/station_state.py
from app.services.station_state import STATION  # noqa: F401 (re-export)
DB_PATH   = f'{STATION}/data/archive_stellaire.db'
# FIXED 2026-05-02 — chemin relatif → absolu via STATION (BUG 2)
WEATHER_DB_PATH = os.path.join(STATION, "weather_bulletins.db")
WEATHER_HISTORY_DIR = f'{STATION}/data/weather_history'
WEATHER_ARCHIVE_DIR = f'{STATION}/data/weather_archive'

# ─── SQLite WAL mode (performance) ──────────────────────────────────────────
def _init_sqlite_wal():
    """Active WAL mode sur toutes les DB SQLite au démarrage."""
    import sqlite3 as _sq
    for _db in [DB_PATH]:
        try:
            _c = _sq.connect(_db)
            _c.execute("PRAGMA journal_mode=WAL")
            _c.execute("PRAGMA synchronous=NORMAL")
            _c.execute("PRAGMA cache_size=10000")
            _c.commit()
            _c.close()
        except Exception as _e:
            print(f"[WAL] {_db}: {_e}")
_init_sqlite_wal()
init_all_wal()   # WAL + busy_timeout sur TOUTES les bases via services/db.py
# ─────────────────────────────────────────────────────────────────────────────


def init_weather_db():
    """Initialise la base locale des bulletins météo (1 an glissant)."""
    try:
        conn = sqlite3.connect(WEATHER_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                hour TEXT,
                temp REAL,
                wind REAL,
                humidity INTEGER,
                pressure REAL,
                wind_direction REAL,
                condition TEXT,
                risk TEXT,
                score INTEGER,
                status TEXT,
                bulletin TEXT,
                source TEXT,
                created_at TEXT,
                UNIQUE(date, hour)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_weather_bulletins_date ON weather_bulletins(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_weather_bulletins_hour ON weather_bulletins(hour)")
        cur.execute("PRAGMA table_info(weather_bulletins)")
        existing_cols = {row[1] for row in cur.fetchall()}
        if "reliability_score" not in existing_cols:
            cur.execute("ALTER TABLE weather_bulletins ADD COLUMN reliability_score INTEGER")
        if "temp_variation" not in existing_cols:
            cur.execute("ALTER TABLE weather_bulletins ADD COLUMN temp_variation REAL")
        if "wind_variation" not in existing_cols:
            cur.execute("ALTER TABLE weather_bulletins ADD COLUMN wind_variation REAL")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WEATHER_DB] init error: {e}")


def _init_weather_history_dir():
    try:
        os.makedirs(WEATHER_HISTORY_DIR, exist_ok=True)
    except Exception as e:
        print(f"[WEATHER_HISTORY] init dir error: {e}")


def _cleanup_weather_history_files():
    try:
        cutoff = datetime.now() - timedelta(days=365)
        for fname in os.listdir(WEATHER_HISTORY_DIR):
            if not fname.endswith(".json"):
                continue
            base = fname[:-5]
            try:
                fdate = datetime.strptime(base, "%Y-%m-%d")
            except Exception:
                continue
            if fdate < cutoff:
                try:
                    os.remove(os.path.join(WEATHER_HISTORY_DIR, fname))
                except Exception:
                    pass
    except Exception as e:
        print(f"[WEATHER_HISTORY] cleanup error: {e}")


def _init_weather_archive_dir():
    try:
        os.makedirs(WEATHER_ARCHIVE_DIR, exist_ok=True)
    except Exception as e:
        print(f"[WEATHER_ARCHIVE] init dir error: {e}")


def _cleanup_weather_archive_files():
    try:
        cutoff = datetime.now() - timedelta(days=365)
        for fname in os.listdir(WEATHER_ARCHIVE_DIR):
            if not fname.endswith(".json"):
                continue
            base = fname[:-5]
            try:
                fdate = datetime.strptime(base, "%Y-%m-%d")
            except Exception:
                continue
            if fdate < cutoff:
                try:
                    os.remove(os.path.join(WEATHER_ARCHIVE_DIR, fname))
                except Exception:
                    pass
    except Exception as e:
        print(f"[WEATHER_ARCHIVE] cleanup error: {e}")


def save_weather_archive_json(data):
    _init_weather_archive_dir()
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(WEATHER_ARCHIVE_DIR, f"{day}.json")
    payload = {
        "date": day,
        "temp": round(float(data.get("temp", 0.0) or 0.0), 1),
        "wind": round(float(data.get("wind", 0.0) or 0.0), 1),
        "humidity": int(data.get("humidity", 0) or 0),
        "pressure": int(round(float(data.get("pressure", 1013) or 1013))),
        "condition": str(data.get("condition") or "Stable"),
        "source": "open-meteo",
        "timestamp": datetime.utcnow().isoformat(),
    }
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WEATHER_ARCHIVE] save error: {e}")
    _cleanup_weather_archive_files()


def save_weather_history_json(data, score, status):
    """Sauvegarde un snapshot météo quotidien en JSON (sans base externe)."""
    _init_weather_history_dir()
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(WEATHER_HISTORY_DIR, f"{day}.json")
    payload = {
        "date": day,
        "temp": round(float(data.get("temp", 0.0)), 1),
        "wind": round(float(data.get("wind", 0.0)), 1),
        "humidity": int(data.get("humidity", 0)),
        "pressure": int(round(float(data.get("pressure", 1015)))),
        "risk": str(data.get("risk") or "FAIBLE"),
        "score": int(score),
        "status": str(status),
    }
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WEATHER_HISTORY] save error: {e}")
    _cleanup_weather_history_files()


def save_weather_bulletin(data):
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H")
    conn = sqlite3.connect(WEATHER_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT temp, wind, humidity, pressure
        FROM weather_bulletins
        ORDER BY date DESC, hour DESC
        LIMIT 1
        """
    )
    prev = cur.fetchone()
    previous_row = dict(prev) if prev else None

    score, status = compute_weather_score(data)
    reliability_score = compute_reliability(data, data.get("source"))
    temp_variation = 0.0
    wind_variation = 0.0
    bulletin = generate_weather_bulletin(data, score, status)
    bulletin += (
        f" Indice de fiabilité des données : {reliability_score}%. "
        f"Variation température : ±{temp_variation:.1f}°C. "
        f"Variation vent : ±{wind_variation:.1f} km/h."
    )
    cur.execute(
        "SELECT id FROM weather_bulletins WHERE date = ? AND hour = ? LIMIT 1",
        (day, hour),
    )
    if cur.fetchone():
        conn.close()
        return {
            "saved": False,
            "score": score,
            "status": status,
            "bulletin": bulletin,
            "reliability_score": reliability_score,
            "temp_variation": temp_variation,
            "wind_variation": wind_variation,
        }

    cur.execute(
        """
        INSERT INTO weather_bulletins
        (date, hour, temp, wind, humidity, pressure, wind_direction, condition, risk, score, status, bulletin, source, created_at, reliability_score, temp_variation, wind_variation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            day,
            hour,
            float(data.get("temp")),
            float(data.get("wind")),
            int(data.get("humidity")),
            float(data.get("pressure", 1015)),
            float(data.get("wind_direction", 0.0)),
            str(data.get("condition") or "Unknown"),
            str(data.get("risk") or "FAIBLE"),
            int(score),
            str(status),
            str(bulletin),
            str(data.get("source") or "Open-Meteo"),
            datetime.now(timezone.utc).isoformat(),
            int(reliability_score),
            float(temp_variation),
            float(wind_variation),
        ),
    )
    cur.execute("DELETE FROM weather_bulletins WHERE date < date('now', '-365 days')")
    conn.commit()
    conn.close()
    return {
        "saved": True,
        "score": score,
        "status": status,
        "bulletin": bulletin,
        "reliability_score": reliability_score,
        "temp_variation": temp_variation,
        "wind_variation": wind_variation,
    }


init_weather_db()
_init_weather_history_dir()
_init_weather_archive_dir()
# ─────────────────────────────────────────────────────────────────────────────
IMG_PATH  = f'{STATION}/telescope_live/current_live.jpg'
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


@app.context_processor
def _inject_seo_site_description():
    """Expose la meta description globale (une seule source : SEO_HOME_DESCRIPTION)."""
    return {'seo_site_description': SEO_HOME_DESCRIPTION}


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
@app.errorhandler(404)
def _astroscan_404(e):
    if request.path.startswith('/api/'):
        return jsonify(error='not_found', path=request.path), 404
    try:
        return render_template('404.html', path=request.path), 404
    except Exception:
        return '<h1>404 — Page introuvable</h1>', 404


@app.errorhandler(500)
def _astroscan_500(e):
    try:
        log.error("500 Internal Error on %s: %s", request.path, e, exc_info=True)
    except Exception:
        pass
    if request.path.startswith('/api/'):
        return jsonify(error='internal_error'), 500
    try:
        return render_template('500.html'), 500
    except Exception:
        return '<h1>500 — Erreur interne</h1>', 500
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


# ── Métriques in-memory pour /status (léger, pas de DB) ─────────────────────
# Fenêtres glissantes : timestamps en time.time(). Lock courte pour limiter la
# contention ; rognage périodique + plafond de taille → O(window) borné, pas de fuite mémoire.
_METRICS_LOCK = threading.Lock()
_METRICS_REQUEST_TIMES: list[float] = []
_METRICS_ERROR_TIMES: list[float] = []
_METRICS_MAX_REQ_BUFFER = 12000


def _metrics_trim_list(ts_list: list[float], horizon_sec: float) -> None:
    cutoff = time.time() - horizon_sec
    ts_list[:] = [t for t in ts_list if t >= cutoff]


def metrics_record_request() -> None:
    """Enregistre une requête HTTP (appelé depuis after_request, hors /static)."""
    try:
        t = time.time()
        with _METRICS_LOCK:
            _METRICS_REQUEST_TIMES.append(t)
            _metrics_trim_list(_METRICS_REQUEST_TIMES, 360)
            if len(_METRICS_REQUEST_TIMES) > _METRICS_MAX_REQ_BUFFER:
                del _METRICS_REQUEST_TIMES[: len(_METRICS_REQUEST_TIMES) - _METRICS_MAX_REQ_BUFFER + 2000]
    except Exception:
        pass


def metrics_record_struct_error() -> None:
    """Compte les événements struct_log au niveau ERROR (observabilité /status)."""
    try:
        t = time.time()
        with _METRICS_LOCK:
            _METRICS_ERROR_TIMES.append(t)
            _metrics_trim_list(_METRICS_ERROR_TIMES, 360)
            if len(_METRICS_ERROR_TIMES) > 4000:
                del _METRICS_ERROR_TIMES[: len(_METRICS_ERROR_TIMES) - 3000]
    except Exception:
        pass


def metrics_status_fields() -> dict:
    """
    Champs additionnels pour /status : erreurs struct_log (niveau ERROR) sur 5 min,
    requêtes non-static sur la dernière minute glissante (débit observé).
    Deux passes sur des listes déjà rognées → coût prévisible même sous charge.
    """
    now = time.time()
    with _METRICS_LOCK:
        e5 = sum(1 for x in _METRICS_ERROR_TIMES if x >= now - 300)
        r60 = sum(1 for x in _METRICS_REQUEST_TIMES if x >= now - 60)
    return {"errors_last_5min": int(e5), "requests_per_min": int(r60)}


# Jeton : limite le volume de logs JSON "http_request" sous fort trafic (stabilité I/O).
_HTTP_LOG_LOCK = threading.Lock()
_HTTP_LOG_TOKENS = 5.0
_HTTP_LOG_MAX = 8.0
_HTTP_LOG_REFILL_PER_SEC = 3.0
_HTTP_LOG_LAST_MONO = time.monotonic()


def _http_request_log_allow() -> bool:
    """True si on peut émettre un struct_log pour une requête 2xx/3xx (anti-spam)."""
    try:
        with _HTTP_LOG_LOCK:
            global _HTTP_LOG_TOKENS, _HTTP_LOG_LAST_MONO
            m = time.monotonic()
            dt = max(0.0, m - _HTTP_LOG_LAST_MONO)
            _HTTP_LOG_LAST_MONO = m
            _HTTP_LOG_TOKENS = min(_HTTP_LOG_MAX, _HTTP_LOG_TOKENS + dt * _HTTP_LOG_REFILL_PER_SEC)
            if _HTTP_LOG_TOKENS >= 1.0:
                _HTTP_LOG_TOKENS -= 1.0
                return True
            return False
    except Exception:
        return True




def struct_log(level: int, **fields) -> None:
    """
    Écrit une ligne structurée dans astroscan_structured.log (via logger racine).
    Utiliser category/event pour filtrer (api, tle, error, ...).
    Les ERROR alimentent errors_last_5min pour /status.
    """
    try:
        if level >= logging.ERROR:
            metrics_record_struct_error()
        lg = logging.getLogger("astroscan")
        msg = str(fields.get("event") or fields.get("msg") or "event")
        lg.log(level, msg, extra={"astroscan_extra": dict(fields)})
    except Exception:
        pass


_structured_json_handler = RotatingFileHandler(
    f"{STATION}/logs/astroscan_structured.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_structured_json_handler.setFormatter(_AstroScanJsonLogFormatter())
logging.getLogger().addHandler(_structured_json_handler)


def system_log(message):
    _orbital_log.info(message)


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

def _health_log_error(component: str, message: str, severity: str = "warn") -> None:
    """
    Structured health error logger.
    - component: short identifier
    - message: human readable
    - severity: info|warn|error|critical
    Maintains a last_error snapshot for /status.
    """
    try:
        sev = (severity or "warn").lower()
        sev = sev if sev in ("info", "warn", "error", "critical") else "warn"
        err = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "component": component,
            "message": str(message),
            "severity": sev,
        }
        HEALTH_STATE["last_error"] = err
        # log using python logging levels (best effort)
        try:
            if sev in ("error", "critical"):
                log.error("HEALTH[%s] %s: %s", component, sev, message)
            elif sev == "warn":
                log.warning("HEALTH[%s] %s: %s", component, sev, message)
            else:
                log.info("HEALTH[%s] %s: %s", component, sev, message)
        except Exception:
            pass
        try:
            lvl = (
                logging.ERROR
                if sev in ("error", "critical")
                else (logging.WARNING if sev == "warn" else logging.INFO)
            )
            struct_log(
                lvl,
                category="health",
                event="health_signal",
                component=component,
                severity=sev,
                message=str(message)[:800],
            )
        except Exception:
            pass
    except Exception:
        pass

def _health_set_error(component: str, message: str, severity: str = "warn") -> None:
    # Backward-compatible alias for earlier calls
    _health_log_error(component, message, severity)

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


def fetch_tle_from_celestrak():
    """Rafraîchit le cache TLE depuis CelesTrak (GP active JSON)."""
    global TLE_CACHE, TLE_CONSECUTIVE_FAILURES, CURRENT_TLE_REFRESH_SECONDS, TLE_LAST_TIMEOUT_LOG_TS
    global TLE_BACKOFF_UNTIL_MONO, TLE_BACKOFF_ACTIVE_LOG_MONO

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
    global TLE_CACHE
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


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_visits_table():
    """Crée la table visits et insère la ligne initiale si besoin."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)
    """)
    conn.execute("INSERT OR IGNORE INTO visits (id, count) VALUES (1, 0)")
    conn.commit()
    conn.close()


def _init_session_tracking_db():
    """Colonne session_id sur visitor_log + table session_time (sans perte de données)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(visitor_log)").fetchall()]
        if cols and "session_id" not in cols:
            cur.execute("ALTER TABLE visitor_log ADD COLUMN session_id TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS session_time (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                path TEXT,
                duration INTEGER,
                created_at TEXT
            )
            """
        )
        # Index légers: accélère stats live, agrégations session et tri temporel.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_ip ON visitor_log(ip)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_session_id ON visitor_log(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_visited_at ON visitor_log(visited_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_country_code ON visitor_log(country_code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_session_time_session_id ON session_time(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_session_time_created_at ON session_time(created_at)")
        # Index UNIQUE sur (ip, session_id) : empêche les doublons entre workers Gunicorn.
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_visitor_log_ip_session "
            "ON visitor_log(ip, COALESCE(session_id, ''))"
        )
        # Nouvelles colonnes visitor_log (ajout sans perte si absentes)
        existing_cols = [r[1] for r in cur.execute("PRAGMA table_info(visitor_log)").fetchall()]
        for col, typedef in [
            ("isp", "TEXT DEFAULT ''"),
            ("human_score", "INTEGER DEFAULT -1"),
            ("is_owner", "INTEGER DEFAULT 0"),
        ]:
            if col not in existing_cols:
                cur.execute(f"ALTER TABLE visitor_log ADD COLUMN {col} {typedef}")
        # Table page_views : chaque vue de page (N par session)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                ip TEXT NOT NULL,
                path TEXT NOT NULL,
                visited_at TEXT NOT NULL DEFAULT (datetime('now')),
                referrer TEXT DEFAULT ''
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_session ON page_views(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_path ON page_views(path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_visited_at ON page_views(visited_at)")
        # Table owner_ips : IPs du propriétaire
        cur.execute("""
            CREATE TABLE IF NOT EXISTS owner_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL UNIQUE,
                label TEXT DEFAULT '',
                added_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


_init_session_tracking_db()
_init_visits_table()


def _curl_get(url, timeout=15):
    """GET via curl — contourne restrictions réseau urllib (Tlemcen)."""
    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '--max-time', str(timeout),
             '-H', 'User-Agent: ORBITAL-CHOHRA/1.0', url],
            capture_output=True, text=True, timeout=timeout + 2
        )
        return (r.stdout or "").strip()
    except Exception as e:
        log.warning(f"curl_get {url[:60]}: {e}")
        return ""


def _curl_post(url, post_data, timeout=15, headers=None):
    """POST via curl (JSON body). Optionnel: headers dict (ex. x-api-key, anthropic-version)."""
    try:
        cmd = ['curl', '-s', '-L', '--max-time', str(timeout),
               '-H', 'User-Agent: ORBITAL-CHOHRA/1.0',
               '-H', 'Content-Type: application/json', '-X', 'POST', '-d', post_data]
        if headers:
            for k, v in headers.items():
                if v is not None and str(v).strip() != '':
                    cmd.extend(['-H', f'{k}: {v}'])
        cmd.append(url)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        return (r.stdout or '').strip()
    except Exception as e:
        log.warning(f"curl_post {url[:60]}: {e}")
        return None


def _curl_post_json(url, payload_dict, extra_headers=None, timeout=15):
    """POST JSON body (dict) avec en-têtes optionnels."""
    body = json.dumps(payload_dict) if isinstance(payload_dict, dict) else payload_dict
    return _curl_post(url, body, timeout=timeout, headers=extra_headers)


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


@app.before_request
def _astroscan_request_timing_start():
    """Timing start pour TOUTES les requêtes + trace route lourde (début)."""
    try:
        g._astroscan_req_start = time.time()
        p = request.path or ""
        heavy_prefixes = (
            "/api/microobservatory/preview/",
            "/api/iss",
            "/api/tle",
            "/api/meteo",
            "/galerie",
            "/module/galerie",
        )
        if any(p.startswith(x) for x in heavy_prefixes):
            _emit_diag_json(
                {
                    "event": "route_trace_start",
                    "path": p,
                    "method": request.method,
                }
            )
    except Exception:
        pass


@app.before_request
def _astroscan_visitor_session_before():
    """Cookie astroscan_sid (identifiant de session navigateur) pour corrélation visitor_log / session_time.
    DOIT s'exécuter AVANT _maybe_increment_visits pour que g._astroscan_sid soit disponible."""
    try:
        if (request.path or "").startswith("/static"):
            return
        sid = request.cookies.get("astroscan_sid")
        if sid:
            g._astroscan_sid = sid
            g._astroscan_sid_new = False
        else:
            g._astroscan_sid = secrets.token_urlsafe(24)
            g._astroscan_sid_new = True
    except Exception:
        try:
            g._astroscan_sid = secrets.token_urlsafe(24)
            g._astroscan_sid_new = True
        except Exception:
            pass


@app.before_request
def _maybe_increment_visits():
    """
    Enregistre les visites de pages HTML (pas les API, static, etc.).
    - page_views : chaque chargement de page (toutes sessions)
    - visitor_log : une entrée par session (IP+session_id unique)
    S'exécute APRÈS _astroscan_visitor_session_before (g._astroscan_sid déjà défini).
    """
    try:
        g._astroscan_req_start = time.time()
    except Exception:
        pass
    if request.path not in PAGE_PATHS:
        return
    _register_unique_visit_from_request(path_override=request.path)


@app.after_request
def _astroscan_struct_log_response(response):
    """Journalise les réponses HTTP (hors static) ; métriques légères + anti-spam logs 2xx/3xx."""
    try:
        p = request.path or ""
        if p.startswith("/static"):
            return response
        # Comptage requêtes (fenêtre glissante) — hors /static pour ne pas polluer le throughput « API ».
        metrics_record_request()
        t0 = getattr(g, "_astroscan_req_start", None)
        dur_ms = None
        if t0 is not None:
            dur_ms = round((time.time() - t0) * 1000, 2)
        # 5xx → struct_log ERROR (alimente errors_last_5min) ; 4xx → WARNING ; 2xx/3xx via jeton (anti-spam).
        sc = response.status_code
        # Instrumentation demandée: timing JSON à partir de 1500 ms.
        if dur_ms is not None and dur_ms >= 1500:
            _emit_diag_json(
                {
                    "event": "request_timing",
                    "path": p,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": dur_ms,
                }
            )
        if dur_ms is not None and dur_ms >= 5000:
            _emit_diag_json(
                {
                    "event": "very_slow_request",
                    "path": p,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": dur_ms,
                }
            )
        # Trace routes lourdes ciblées (fin).
        heavy_prefixes = (
            "/api/microobservatory/preview/",
            "/api/iss",
            "/api/tle",
            "/api/meteo",
            "/galerie",
            "/module/galerie",
        )
        if dur_ms is not None and any((p or "").startswith(x) for x in heavy_prefixes):
            try:
                print(f"[DEBUG] route {p} took {dur_ms:.1f} ms", flush=True)
            except Exception:
                pass
            try:
                log.info("[DEBUG] route %s took %.1f ms", p, dur_ms)
            except Exception:
                pass

        # Signalement struct_log existant conservé (anti-régression).
        if dur_ms is not None and dur_ms >= 2500:
            struct_log(
                logging.WARNING,
                category="api",
                event="slow_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
        if sc >= 500:
            struct_log(
                logging.ERROR,
                category="api",
                event="http_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
        elif sc >= 400:
            struct_log(
                logging.WARNING,
                category="api",
                event="http_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
        elif _http_request_log_allow():
            struct_log(
                logging.INFO,
                category="api",
                event="http_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
    except Exception:
        pass
    return response


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


def _analytics_tz_for_country_code(code):
    """Fuseau indicatif pour heure locale (US / DZ / BR)."""
    c = (code or "").strip().upper()
    if c == "US":
        return "America/Los_Angeles"
    if c == "DZ":
        return "Africa/Algiers"
    if c == "BR":
        return "America/Sao_Paulo"
    return "UTC"


def _analytics_fmt_duration_sec(sec):
    """Ex. 125 → 2m05."""
    try:
        s = int(sec)
    except Exception:
        return "—"
    s = max(0, s)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}"
    if m > 0:
        return f"{m}m{s:02d}"
    return f"{s}s"


def _analytics_journey_display(journey_raw):
    if not journey_raw:
        return "—"
    parts = [p.strip() for p in str(journey_raw).split(",") if p.strip()]
    if not parts:
        return "—"
    return " → ".join(parts)


def _analytics_start_local_display(start_iso, country_code):
    """Heure locale au début de session selon country_code."""
    try:
        from zoneinfo import ZoneInfo

        raw = (start_iso or "").strip()
        if not raw:
            return "—"
        tzname = _analytics_tz_for_country_code(country_code)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tzname))
        return local.strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return (start_iso or "—") if start_iso else "—"


def _analytics_time_hms_local(iso_str, country_code):
    """Heure locale HH:MM:SS pour une ligne de timeline."""
    try:
        from zoneinfo import ZoneInfo

        raw = (iso_str or "").strip()
        if not raw:
            return "—"
        tzname = _analytics_tz_for_country_code(country_code)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tzname))
        return local.strftime("%H:%M:%S")
    except Exception:
        return "—"


def _analytics_session_classification(total_sec, page_count):
    """Profil comportemental (nombre de vues = lignes session_time)."""
    try:
        t = int(total_sec)
    except Exception:
        t = 0
    try:
        n = int(page_count)
    except Exception:
        n = 0
    if t > 180 and n > 5:
        return "Inspection approfondie"
    if n > 3:
        return "Exploration active"
    return "Passage rapide"


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

_IMAGE_CACHE_TTL = 300  # 5 min — APOD/Hubble/archive changent peu
def _source_path(s):
    return Path(f'{STATION}/telescope_live/source_{s}.jpg')

def _fetch_apod_live():
    """Image du jour NASA APOD — temps 0 (API en _curl_get, image en urllib pour binaire)."""
    try:
        key = (os.environ.get('NASA_API_KEY') or 'DEMO_KEY').strip()
        raw = _curl_get(f'https://api.nasa.gov/planetary/apod?api_key={key}', timeout=14)
        if not raw:
            return None, None, None
        d = json.loads(raw)
        if d.get('media_type') != 'image':
            return None, None, None
        url = d.get('hdurl') or d.get('url')
        if not url:
            return None, None, None
        import urllib.request as urlreq
        with urlreq.urlopen(urlreq.Request(url, headers={'User-Agent': 'ORBITAL-CHOHRA/1.0'}), timeout=25) as img:
            data = img.read()
        return data, d.get('title', 'APOD'), 'NASA APOD'
    except Exception as e:
        log.warning(f"fetch apod: {e}")
        return None, None, None

def _fetch_hubble_archive():
    """Image Hubble issue des archives ESA (6 images iconiques, sélection aléatoire).
    Note : images d'archive 1994-2020, pas une observation en cours."""
    urls = [
        ("Pilliers de la Création — M16 (1995)", "https://esahubble.org/media/archives/images/screen/heic1501a.jpg"),
        ("Galaxie du Tourbillon M51 (2005)", "https://esahubble.org/media/archives/images/screen/heic0506a.jpg"),
        ("Nébuleuse de la Carène (2007)", "https://esahubble.org/media/archives/images/screen/heic0707a.jpg"),
        ("Galaxie d'Andromède M31 (2015)", "https://esahubble.org/media/archives/images/screen/heic1502a.jpg"),
        ("Nébuleuse Œil de Chat (2004)", "https://esahubble.org/media/archives/images/screen/heic0403a.jpg"),
        ("Jupiter — Grande Tache Rouge (2019)", "https://esahubble.org/media/archives/images/screen/heic1920a.jpg"),
    ]
    import random
    title, url = random.choice(urls)
    try:
        import urllib.request as urlreq
        req = urlreq.Request(url, headers={'User-Agent': 'ORBITAL-CHOHRA/1.0'})
        with urlreq.urlopen(req, timeout=25) as r:
            data = r.read()
        if len(data) < 10000:
            return None, None, None
        return data, title, 'Archives ESA/Hubble'
    except Exception as e:
        log.warning(f"fetch hubble archive: {e}")
        return None, None, None

# Alias de compatibilité pour le code existant
_fetch_hubble_live = _fetch_hubble_archive

def _fetch_apod_archive_live():
    """NASA APOD — image d'archive aléatoire (2015-2024). Honnête : pas l'image du jour."""
    try:
        import urllib.request as urlreq
        import random
        key = os.environ.get('NASA_API_KEY', 'DEMO_KEY')
        y, m = random.randint(2015, 2024), random.randint(1, 12)
        d = random.randint(1, 28)
        date = f'{y}-{m:02d}-{d:02d}'
        with urlreq.urlopen(
            f'https://api.nasa.gov/planetary/apod?api_key={key}&date={date}', timeout=12
        ) as r:
            data_j = json.loads(r.read())
        if data_j.get('media_type') != 'image':
            return None, None, None
        url = data_j.get('hdurl') or data_j.get('url')
        with urlreq.urlopen(urlreq.Request(url, headers={'User-Agent': 'ORBITAL-CHOHRA/1.0'}), timeout=25) as img:
            data = img.read()
        return data, data_j.get('title', 'APOD') + f' ({date})', f'NASA APOD {date}'
    except Exception as e:
        log.warning(f"fetch apod archive: {e}")
        return None, None, None

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


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE NOCTURNE — HARVARD MICROOBSERVATORY · SÉLECTION TLEMCEN
# Sélectionne 3 objets visibles ce soir, télécharge les vrais FITS Harvard,
# convertit en JPG et stocke avec métadonnées de capture.
# ══════════════════════════════════════════════════════════════════════════════

_MO_DIR_URL  = "https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/ImageDirectory.php"
_MO_DL_BASE  = "https://mo-www.cfa.harvard.edu/ImageDirectory/"   # URL réelle de téléchargement FITS

# Correspondance préfixes MO → coordonnées + labels FR
_MO_OBJECT_CATALOG = {
    'Moon':         {'ra': None,   'dec': None,   'type': 'Satellite nat.', 'label': 'Lune',                 'body': 'moon'},
    'Jupiter':      {'ra': None,   'dec': None,   'type': 'Planète',        'label': 'Jupiter',              'body': 'jupiter'},
    'Pluto':        {'ra': None,   'dec': None,   'type': 'Planète naine',  'label': 'Pluton',               'body': 'pluto'},
    'AndromedaGal': {'ra': 10.68,  'dec': 41.27,  'type': 'Galaxie',        'label': 'M31 — Andromède'},
    'OrionNebula':  {'ra': 83.82,  'dec': -5.39,  'type': 'Nébuleuse',      'label': 'M42 — Orion'},
    'OrionNebulaM': {'ra': 83.82,  'dec': -5.39,  'type': 'Nébuleuse',      'label': 'M42 — Orion'},
    'Pleiades':     {'ra': 56.87,  'dec': 24.12,  'type': 'Amas ouvert',    'label': 'M45 — Pléiades'},
    'HerculesClus': {'ra': 250.42, 'dec': 36.46,  'type': 'Amas glob.',     'label': 'M13 — Hercule'},
    'RingNebulaM5': {'ra': 283.40, 'dec': 33.03,  'type': 'Nébuleuse plan.','label': 'M57 — Lyre'},
    'DumbbellNebu': {'ra': 299.90, 'dec': 22.72,  'type': 'Nébuleuse plan.','label': 'M27 — Haltère'},
    'M-81SpiralGa': {'ra': 148.89, 'dec': 69.07,  'type': 'Galaxie',        'label': 'M81 — Bode'},
    'NGC3031M81':   {'ra': 148.89, 'dec': 69.07,  'type': 'Galaxie',        'label': 'M81 — Bode'},
    'M-51Whirlpoo': {'ra': 202.47, 'dec': 47.20,  'type': 'Galaxie',        'label': 'M51 — Tourbillon'},
    'CrabNebulaM1': {'ra': 83.63,  'dec': 22.01,  'type': 'Reste supernova','label': 'M1 — Crabe'},
    'M-101SpiralG': {'ra': 210.80, 'dec': 54.35,  'type': 'Galaxie',        'label': 'M101 — Épinglier'},
    'NGC5457M101':  {'ra': 210.80, 'dec': 54.35,  'type': 'Galaxie',        'label': 'NGC5457/M101'},
    'LagoonNebula': {'ra': 270.92, 'dec': -24.38, 'type': 'Nébuleuse',      'label': 'M8 — Lagune'},
    'EagleNebulaM': {'ra': 274.70, 'dec': -13.79, 'type': 'Nébuleuse',      'label': 'M16 — Aigle'},
    'RosetteNebul': {'ra': 97.65,  'dec': 4.93,   'type': 'Nébuleuse',      'label': 'Nébuleuse de la Rosette'},
    'Quasar3C273':  {'ra': 187.28, 'dec': 2.05,   'type': 'Quasar',         'label': 'Quasar 3C 273'},
    'M87':          {'ra': 187.71, 'dec': 12.39,  'type': 'Galaxie géante', 'label': 'M87 — Virgo'},
    'SombreroGala': {'ra': 190.00, 'dec': -11.62, 'type': 'Galaxie',        'label': 'M104 — Sombrero'},
    'SagittariusA': {'ra': 266.42, 'dec': -29.01, 'type': 'Noyau galactique','label': 'Sgr A* — Centre galactique'},
    'MilkyWay':     {'ra': 266.42, 'dec': -29.01, 'type': 'Voie Lactée',   'label': 'Voie Lactée — Cœur galactique'},
    'OpenClusterM': {'ra': 92.27,  'dec': 24.33,  'type': 'Amas ouvert',   'label': 'Amas ouvert — Gémeaux'},
    'NGC891':       {'ra': 35.64,  'dec': 42.35,  'type': 'Galaxie',        'label': 'NGC 891'},
    'CentaurusA':   {'ra': 201.36, 'dec': -43.02, 'type': 'Galaxie radio',  'label': 'Cen A / NGC 5128'},
    'Messier15':    {'ra': 322.49, 'dec': 12.17,  'type': 'Amas glob.',     'label': 'M15 — Pégase'},
    'BetaLyr':      {'ra': 282.52, 'dec': 33.36,  'type': 'Étoile double',  'label': 'Beta Lyrae'},
    'CygnusX-1':    {'ra': 299.59, 'dec': 35.20,  'type': 'Trou noir binaire','label': 'Cygnus X-1'},
    'Algol':        {'ra': 47.04,  'dec': 40.96,  'type': 'Étoile variable','label': 'Algol (β Persei)'},
    'DeltaCephei':  {'ra': 337.29, 'dec': 58.42,  'type': 'Céphéide',       'label': 'Delta Cephei'},
    'M-82Irregula': {'ra': 148.97, 'dec': 69.68,  'type': 'Galaxie irr.',   'label': 'M82 — Cigare'},
    'M82Irregular': {'ra': 148.97, 'dec': 69.68,  'type': 'Galaxie irr.',   'label': 'M82 — Cigare'},
    'NGC4579M58':   {'ra': 189.43, 'dec': 11.82,  'type': 'Galaxie',        'label': 'M58 — Virgo'},
    'NGC3351M95':   {'ra': 160.99, 'dec': 11.70,  'type': 'Galaxie',        'label': 'M95 — Leo'},
    'BeehiveClust': {'ra': 130.10, 'dec': 19.67,  'type': 'Amas ouvert',   'label': 'M44 — La Ruche'},
    'M-82Irregula': {'ra': 148.97, 'dec': 69.68,  'type': 'Galaxie irr.',   'label': 'M82 — Cigare'},
}


def _mo_parse_filename(name):
    """Parse 'ObjectName260422221047.FITS' → dict avec prefix, captured_at, url."""
    stem = os.path.splitext(name)[0]
    m = re.search(r'^(.+?)(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$', stem)
    if not m:
        return None
    prefix = m.group(1)
    yy, mo, dd, hh, mi, ss = m.groups()[1:]
    try:
        dt = datetime(2000 + int(yy), int(mo), int(dd), int(hh), int(mi), int(ss), tzinfo=timezone.utc)
    except ValueError:
        return None
    return {'prefix': prefix, 'filename': name, 'captured_at': dt, 'url': _MO_DL_BASE + name}


def _mo_fetch_catalog_today():
    """
    Lit le répertoire MicroObservatory et retourne {prefix → [entries]}
    pour les 30 derniers jours. Cache 1h.
    """
    from datetime import timedelta

    cached = cache_get('mo_catalog_today', 3600)
    if cached is not None:
        return cached

    html = _curl_get(_MO_DIR_URL, timeout=25) or ""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    catalog = {}
    for name in re.findall(r'\b([\w\-]+\d{12}\.FITS)\b', html, re.I):
        parsed = _mo_parse_filename(name)
        if not parsed or parsed['captured_at'] < cutoff:
            continue
        prefix = parsed['prefix']
        if prefix not in catalog:
            catalog[prefix] = []
        catalog[prefix].append(parsed)

    for k in catalog:
        catalog[k].sort(key=lambda x: x['captured_at'], reverse=True)

    cache_set('mo_catalog_today', catalog)
    log.info('mo_fetch_catalog_today: %d préfixes d\'objets trouvés', len(catalog))
    return catalog


def _mo_visible_tonight():
    """
    Retourne les objets MO visibles depuis Tlemcen à 23h00 UTC (nuit locale),
    triés par altitude décroissante.
    """
    from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_body
    from astropy.time import Time
    import astropy.units as u

    location = EarthLocation(lat=34.87*u.deg, lon=1.32*u.deg, height=816*u.m)
    # 23:00 UTC = 00:00 locale Tlemcen (UTC+1)
    t_obs = Time(int(Time.now().jd) + 23/24.0, format='jd')
    frame = AltAz(obstime=t_obs, location=location)

    visible = []
    seen_labels = set()

    for prefix, info in _MO_OBJECT_CATALOG.items():
        try:
            if info.get('body'):
                if info['body'] == 'sun':
                    continue
                coord = get_body(info['body'], t_obs, location)
                altaz = coord.transform_to(frame)
                alt = float(altaz.alt.deg)
            elif info.get('ra') is not None:
                coord = SkyCoord(ra=info['ra']*u.deg, dec=info['dec']*u.deg, frame='icrs')
                altaz = coord.transform_to(frame)
                alt = float(altaz.alt.deg)
            else:
                continue
        except Exception:
            continue

        label = info['label']
        if alt > 20 and label not in seen_labels:
            seen_labels.add(label)
            visible.append({'prefix': prefix, 'alt': round(alt, 1), **info})

    visible.sort(key=lambda x: -x['alt'])
    return visible


def _mo_fits_to_jpg(fits_bytes, save_path):
    """Convertit des octets FITS en JPG avec étirement ZScale + colormap hot."""
    import io, numpy as np
    from astropy.io import fits as _fits
    from astropy.visualization import ZScaleInterval
    from PIL import Image

    with _fits.open(io.BytesIO(fits_bytes)) as hdul:
        data = hdul[0].data
        header = hdul[0].header
        captured_hdr = header.get('DATE-OBS', header.get('DATE', ''))

    if data is None:
        raise ValueError('FITS data vide')

    while hasattr(data, 'ndim') and data.ndim > 2:
        data = data[0]
    arr = np.nan_to_num(np.asarray(data, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)

    interval = ZScaleInterval()
    try:
        vmin, vmax = interval.get_limits(arr)
    except Exception:
        vmin = float(np.percentile(arr, 2))
        vmax = float(np.percentile(arr, 98))
    if vmax <= vmin:
        vmax = vmin + 1.0

    norm = np.clip((arr - vmin) / (vmax - vmin), 0.0, 1.0)
    r = np.clip(norm * 255,       0, 255).astype(np.uint8)
    g = np.clip(norm * 155,       0, 255).astype(np.uint8)
    b = np.clip(norm * 55  - 10,  0, 255).astype(np.uint8)

    pil = Image.fromarray(np.stack([r, g, b], axis=2), 'RGB').resize((600, 600), Image.LANCZOS)
    pil.save(save_path, 'JPEG', quality=92, optimize=True)
    return captured_hdr


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

from datetime import datetime as _dt_utc


# MIGRATED TO api_bp PASS 11 — /api/v1/asteroids → see app/blueprints/api/__init__.py (api_v1_asteroids)


# MIGRATED TO weather_bp PASS 7 — /api/v1/solar-weather → see app/blueprints/weather/__init__.py (api_v1_solar)
# MIGRATED TO astro_bp PASS 7 — /api/v1/tonight → see app/blueprints/astro/__init__.py (api_v1_tonight)


def _fetch_voyager():
    """Position Voyager 1 & 2 via NASA JPL Horizons (curl)."""
    try:
        now = _dt_utc.utcnow()
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
        today = _dt_utc.utcnow().date().isoformat()
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
        cutoff = _dt.datetime.utcnow() - _dt.timedelta(hours=24)
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
                    issued_dt = _dt.datetime.utcnow()
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


def log_rejected_image(metadata, reason):
    """Log a rejected laboratory image into a JSON log file."""
    try:
        path = os.path.join(LAB_LOGS_DIR, "rejected_images.json")
        record = {
            "metadata": metadata,
            "reason": reason,
            "timestamp": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        log.warning("log_rejected_image failed: %s", e)


def save_normalized_metadata(meta_dict):
    """Persist a normalized metadata dict to METADATA_DB."""
    try:
        filename = meta_dict.get("local_filename") or meta_dict.get("filename")
        if not filename:
            return
        meta_path = os.path.join(METADATA_DB, str(filename) + ".json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, indent=2)
    except Exception as e:
        log.warning("save_normalized_metadata failed: %s", e)


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


def _download_nasa_apod():
    """Télécharge l'image du jour NASA APOD vers RAW_IMAGES + métadonnées JSON."""
    import urllib.request
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        url = f"https://api.nasa.gov/planetary/apod?api_key={api_key}&count=1"
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=28) as resp:
            payload = _safe_json_loads(resp.read(), "lab_apod")
            if payload is None:
                return
            data = payload[0] if isinstance(payload, list) and payload else payload
            if not isinstance(data, dict):
                return
            if data.get("url") and data.get("media_type") == "image":
                from datetime import datetime as _dt
                img_url = data["url"]
                ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
                safe_date = (data.get("date") or _dt.utcnow().strftime("%Y-%m-%d")).replace("-", "")
                filename = f"apod_{safe_date}{ext}"
                path = os.path.join(RAW_IMAGES, filename)
                urllib.request.urlretrieve(img_url, path)
                meta = {
                    "source": "NASA APOD",
                    "telescope": "various",
                    "date": data.get("date", ""),
                    "object_name": data.get("title", ""),
                    "filename": filename,
                }
                meta_path = os.path.join(METADATA_DB, filename + ".json")
                with open(meta_path, "w", encoding="utf-8") as fp:
                    json.dump(meta, fp, indent=2)
                saved.append(filename)
    except Exception as e:
        log.debug("download_nasa_apod: %s", e)
    if saved:
        log.info("Lab: saved NASA APOD %s", saved)


def _download_hubble_images():
    """Télécharge un petit lot d'images Hubble vers RAW_IMAGES + métadonnées JSON."""
    import urllib.request
    base_url = "https://hubblesite.org/api/v3"
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        # Limiter le nombre d'images pour rester léger
        index_url = f"{base_url}/images?page=1"
        req = urllib.request.Request(index_url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            images = _safe_json_loads(resp.read(), "lab_hubble_index")
        if not isinstance(images, list):
            return
        # images est une liste de dicts avec au moins un id
        for img in images[:5]:
            img_id = img.get("id")
            if not img_id:
                continue
            detail_url = f"{base_url}/image/{img_id}"
            dreq = urllib.request.Request(detail_url, headers={"User-Agent": "AstroScan-Lab/1.0"})
            with urllib.request.urlopen(dreq, timeout=20) as dresp:
                detail = _safe_json_loads(dresp.read(), "lab_hubble_detail")
            if not isinstance(detail, dict):
                continue
            files = detail.get("image_files") or []
            if not files:
                continue
            # dernier élément = meilleure résolution
            file_url = files[-1].get("file_url")
            if not file_url:
                continue
            filename = f"hubble_{img_id}.jpg"
            path = os.path.join(RAW_IMAGES, filename)
            urllib.request.urlretrieve(file_url, path)
            meta = {
                "source": "HUBBLE",
                "telescope": "HST",
                "date": detail.get("release_date", ""),
                "object_name": detail.get("name", "") or detail.get("mission", ""),
                "filename": filename,
            }
            meta_path = os.path.join(METADATA_DB, filename + ".json")
            with open(meta_path, "w", encoding="utf-8") as fp:
                json.dump(meta, fp, indent=2)
            saved.append(filename)
    except Exception as e:
        log.debug("download_hubble_images: %s", e)
    if saved:
        log.info("Lab: saved Hubble images %s", saved)


def _download_jwst_images():
    """Télécharge des images JWST vers RAW_IMAGES + métadonnées JSON."""
    import urllib.request
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        url = "https://webbtelescope.org/api/v1/images"
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = _safe_json_loads(resp.read(), "lab_jwst")
        if data is None:
            return
        items = data if isinstance(data, list) else (data.get("items", data.get("images", [])) or [])
        for i, item in enumerate(items[:3]):
            img_url = item.get("image_url") or item.get("url") or item.get("file_url") or (item.get("image", {}) or {}).get("url")
            if not img_url:
                continue
            ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
            filename = f"jwst_{int(time.time())}_{i}{ext}"
            path = os.path.join(RAW_IMAGES, filename)
            urllib.request.urlretrieve(img_url, path)
            meta = {
                "source": "JWST",
                "telescope": "James Webb",
                "filename": filename,
            }
            meta_path = os.path.join(METADATA_DB, filename + ".json")
            with open(meta_path, "w", encoding="utf-8") as fp:
                json.dump(meta, fp, indent=2)
            saved.append(filename)
    except Exception as e:
        log.debug("download_jwst_images: %s", e)
    if saved:
        log.info("Lab: saved JWST images %s", saved)


def _download_esa_images():
    """
    Images « agences spatiales » pour le Lab.
    L'endpoint historique esa.int/api/images renvoie 404 — repli NASA Images API (JSON stable).
    """
    import urllib.parse
    import urllib.request
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        q = urllib.parse.quote("satellite mission")
        url = f"https://images-api.nasa.gov/search?q={q}&media_type=image&page_size=10"
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=28) as resp:
            root = _safe_json_loads(resp.read(), "lab_nasa_images")
        if not isinstance(root, dict):
            return
        items = (root.get("collection") or {}).get("items") or []
        for i, it in enumerate(items[:4]):
            if not isinstance(it, dict):
                continue
            img_url = None
            for L in it.get("links") or []:
                if not isinstance(L, dict):
                    continue
                href = (L.get("href") or "").strip()
                if not href:
                    continue
                low = href.lower()
                if any(x in low for x in (".jpg", ".jpeg", ".png", ".webp")):
                    img_url = href
                    break
            if not img_url:
                continue
            ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
            filename = f"esa_{int(time.time())}_{i}{ext}"
            path = os.path.join(RAW_IMAGES, filename)
            try:
                urllib.request.urlretrieve(img_url, path)
            except Exception:
                continue
            meta = {
                "source": "NASA Images (flux Lab agences)",
                "telescope": "multi",
                "filename": filename,
            }
            meta_path = os.path.join(METADATA_DB, filename + ".json")
            with open(meta_path, "w", encoding="utf-8") as fp:
                json.dump(meta, fp, indent=2)
            saved.append(filename)
    except Exception as e:
        log.debug("download_esa_images: %s", e)
    if saved:
        log.info("Lab: saved agency-slot images %s", saved)


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


@app.after_request
def _astroscan_session_cookie_and_time_script(response):
    """Pose le cookie astroscan_sid + injecte le script de durée de page (HTML uniquement)."""
    try:
        p = request.path or ""
        if p.startswith("/static"):
            return response
        secure = bool(request.is_secure) or (
            (request.headers.get("X-Forwarded-Proto") or "").lower() == "https"
        )
        # Rafraîchit le cookie à chaque page HTML : session = 30 min d'inactivité.
        # Si inactif > 30 min → cookie expire → prochaine visite = nouvelle session.
        if getattr(g, "_astroscan_sid", None):
            response.set_cookie(
                "astroscan_sid",
                g._astroscan_sid,
                max_age=60 * 30,  # 30 minutes d'inactivité = nouvelle session
                samesite="Lax",
                path="/",
                secure=secure,
            )
        ct = (response.headers.get("Content-Type") or "").lower()
        if response.status_code >= 400 or "text/html" not in ct:
            return response
        data = response.get_data(as_text=True)
        if "astroscan-session-time" in data or "</body>" not in data:
            return response
        data = data.replace("</body>", _SESSION_TIME_SNIPPET + "\n</body>", 1)
        response.set_data(data)
    except Exception:
        pass
    return response


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
