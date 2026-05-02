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

import os, sys, json, sqlite3, re, time, random, logging, subprocess, glob, threading, requests, hashlib, secrets, fcntl, base64
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ─── OBSERVABILITÉ — SENTRY ─────────────────────────────────────────────────
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,
        environment=os.environ.get("FLASK_ENV", "production"),
        release="astroscan@2.0.0"
    )
    print("[SENTRY] Monitoring actif")
# ─────────────────────────────────────────────────────────────────────────────
from flask import (Flask, render_template, jsonify, request, g,
                   redirect, send_file, send_from_directory, Response, abort,
                   make_response, stream_with_context)
from werkzeug.utils import secure_filename
from app.services.orbit_sgp4 import propagate_tle_debug
from app.services.satellites import SATELLITES, list_satellites, get_satellite_tle_name_map
from app.services.accuracy_history import get_accuracy_history, get_accuracy_stats
from app.routes.iss import api_iss_impl
# MIGRATED TO sdr_bp 2026-05-02 — see app/blueprints/sdr/routes.py
# from app.routes.sdr import api_sdr_passes_impl
# MIGRATED TO apod_bp 2026-05-02 — see app/blueprints/apod/routes.py
# from app.routes.apod import apod_fr_json_impl, apod_fr_view_impl
from services.stats_service import get_global_stats, get_top_countries, get_today_visitors, get_distinct_countries
from services.weather_service import (
    interpretWeatherCode, compute_weather_score, generate_weather_bulletin,
    normalize_weather, compute_reliability, compute_weather_reliability,
    validate_data, compute_risk, _internal_weather_fallback, _derive_weather_condition,
    _safe_kp_value, _kp_premium_profile, _build_local_weather_payload,
    get_weather_snapshot, get_kp_index, get_aurora_data, get_space_weather,
)
from services.nasa_service import (
    get_api_key as _nasa_api_key, fetch_nasa_json,
    _fetch_nasa_apod, _fetch_nasa_neo, _fetch_nasa_solar,
    get_apod_data, get_neo_feed, get_space_events,
)
from services.orbital_service import (
    compute_tle_risk_signal, build_final_core, normalize_celestrak_record,
    get_iss_position, get_iss_orbit, load_tle_data, compute_satellite_track,
)
from services.cache_service import (
    ANALYTICS_CACHE,
    cache_get, cache_set, cache_cleanup,
    get_cached, invalidate_cache, invalidate_all, cache_status,
)
from services.ephemeris_service import (
    get_sun_ephemeris, get_moon_ephemeris,
    get_moon_phase as get_ephemeris_moon_phase,
    get_twilight_times, get_full_ephemeris,
)
from services.utils import (
    _is_bot_user_agent, _parse_iso_to_epoch_seconds,
    _safe_json_loads, safe_ensure_dir, _detect_lang,
)
from services.db import get_db as get_db_ctx, init_all_wal
from services.circuit_breaker import (
    CB_NASA, CB_N2YO, CB_NOAA, CB_ISS, CB_METEO, CB_TLE, CB_GROQ,
    all_status as _cb_all_status,
)
from services import config as _cfg

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


START_TIME = time.time()
# Passe à True en fin de chargement du module (après routes + init TLE) — utilisé par GET /ready.
server_ready = False

CLAUDE_CALL_COUNT = 0
CLAUDE_MAX_CALLS = 100
CLAUDE_80_WARNING_SENT = False
GROQ_CALL_COUNT = 0
COLLECTOR_LAST_RUN = 0

# ── Config ──────────────────────────────────────────────────
STATION   = '/root/astro_scan'
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

# ── Blueprints ────────────────────────────────────────────────────────────────
from app.blueprints.seo.routes import seo_bp
app.register_blueprint(seo_bp)
# Blueprint APOD — added 2026-05-02 (PHASE 2B B1)
from app.blueprints.apod.routes import apod_bp
app.register_blueprint(apod_bp)
# Blueprint SDR — added 2026-05-02 (PHASE 2B B2)
from app.blueprints.sdr.routes import sdr_bp
app.register_blueprint(sdr_bp)
# Blueprint ISS — added 2026-05-02 (PHASE 2B B3b)
from app.blueprints.iss.routes import iss_bp
app.register_blueprint(iss_bp)
# Blueprint i18n — added 2026-05-02 (PHASE 2B B-RECYCLE R1)
from app.blueprints.i18n import bp as i18n_bp
app.register_blueprint(i18n_bp)
# Blueprint api — added 2026-05-02 (PHASE 2B B-RECYCLE R2)
from app.blueprints.api import bp as api_bp
app.register_blueprint(api_bp)
# Blueprint pages — added 2026-05-02 (PHASE 2B B-RECYCLE R2, partial)
# /landing deferred — see /tmp/pages_init_patched_TODO.md
from app.blueprints.pages import bp as pages_bp
app.register_blueprint(pages_bp)
# Blueprint main — added 2026-05-02 (PHASE 2B B-RECYCLE R3)
from app.blueprints.main import bp as main_bp
app.register_blueprint(main_bp)

from app.blueprints.system import bp as system_bp
app.register_blueprint(system_bp)


@app.context_processor
def _inject_seo_site_description():
    """Expose la meta description globale (une seule source : SEO_HOME_DESCRIPTION)."""
    return {'seo_site_description': SEO_HOME_DESCRIPTION}


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
try:
    from core import status_engine as _core_status_engine
except Exception:
    _core_status_engine = None


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


_API_RATE_LOCK = threading.Lock()
_API_RATE_HITS: dict[str, list[float]] = {}


def _api_rate_limit_allow(key: str, limit: int, window_sec: int) -> tuple[bool, int]:
    """
    Fenêtre glissante simple anti-abus.
    Retourne (allowed, retry_after_sec).
    """
    now = time.time()
    try:
        with _API_RATE_LOCK:
            hits = _API_RATE_HITS.get(key, [])
            cutoff = now - float(window_sec)
            hits = [t for t in hits if t >= cutoff]
            if len(hits) >= int(limit):
                retry_after = max(1, int(window_sec - (now - hits[0])))
                _API_RATE_HITS[key] = hits
                return False, retry_after
            hits.append(now)
            _API_RATE_HITS[key] = hits
            # Garde-fou mémoire (rare)
            if len(_API_RATE_HITS) > 8000:
                for k in list(_API_RATE_HITS.keys())[:1500]:
                    arr = _API_RATE_HITS.get(k) or []
                    if not arr or arr[-1] < now - 3600:
                        _API_RATE_HITS.pop(k, None)
            return True, 0
    except Exception:
        return True, 0


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
TLE_CACHE_FILE = f"{STATION}/data/tle_active_cache.json"

TLE_CACHE = {
    "status": "cached",
    "source": "CelesTrak GP active",
    "last_refresh_iso": None,
    "count": 0,
    "items": [],
    "error": None,
}

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
        TLE_CACHE = {
            "status": "connected",
            "source": "CelesTrak GP active JSON",
            "last_refresh_iso": ts,
            "count": len(items),
            "items": items,
            "error": None,
        }
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
                        TLE_CACHE = {
                            "status": "cached",
                            "source": "Local active.tle fallback",
                            "last_refresh_iso": TLE_CACHE.get("last_refresh_iso") or ts,
                            "count": len(parsed_items),
                            "items": parsed_items,
                            "error": msg,
                        }
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


# Initialiser le cache TLE au démarrage de l'application
try:
    load_tle_cache_from_disk()
    # premier rafraîchissement non bloquant
    try:
        fetch_tle_from_celestrak()
    except Exception:
        pass
    t = threading.Thread(target=tle_refresh_loop, daemon=True)
    t.start()
except Exception as e:
    _orbital_log.warning(f"[TLE] init failed: {e}")

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


def _get_visits_count():
    """Retourne le nombre actuel de visites."""
    conn = get_db()
    row = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()
    conn.close()
    return row[0] if row else 0


def _increment_visits():
    """Incrémente le compteur de visites et retourne la nouvelle valeur."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE visits SET count = count + 1 WHERE id=1")
    new_count = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()[0]
    conn.commit()
    conn.close()
    return new_count

def _gemini_translate(text, obs_id=None):
    """Traduit EN→FR via Gemini. Met en cache dans DB."""
    if not text or len(text) < 15:
        return text
    if not _detect_lang(text):
        return text  # Déjà en français
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        return text
    try:
        import urllib.request as urlreq
        import urllib.error as urlerr
        # In-memory cache + anti-flood (max 1 req/s)
        global TRANSLATE_CACHE, TRANSLATE_LAST_REQUEST_TS
        lang = "fr"
        raw_key = (text[:1500] + "|" + lang).encode("utf-8", errors="ignore")
        cache_key = hashlib.sha256(raw_key).hexdigest()
        now_ts = time.time()
        item = TRANSLATE_CACHE.get(cache_key)
        if item and (now_ts - item.get("ts", 0) < TRANSLATE_TTL_SECONDS):
            return item.get("value", text)

        # Max 1 request per second; if too soon, return original text (no error).
        if now_ts - TRANSLATE_LAST_REQUEST_TS < 1.0:
            return text

        payload = json.dumps({'contents': [{'parts': [{'text':
            "Traduis ce texte astronomique en français fluide et naturel. "
            "Réponds UNIQUEMENT avec la traduction, sans guillemets ni commentaires.\n\n"
            + text[:1500]
        }]}]}).encode()
        req = urlreq.Request(
            f'https://generativelanguage.googleapis.com/v1beta/models/'
            f'gemini-2.0-flash:generateContent?key={api_key}',
            data=payload, headers={'Content-Type': 'application/json'}
        )
        TRANSLATE_LAST_REQUEST_TS = time.time()
        with urlreq.urlopen(req, timeout=12) as r:
            result = json.loads(r.read())
        translated = result['candidates'][0]['content']['parts'][0]['text'].strip()
        try:
            TRANSLATE_CACHE[cache_key] = {"value": translated or text, "ts": time.time()}
        except Exception:
            pass
        if obs_id and translated:
            try:
                c = sqlite3.connect(DB_PATH)
                c.execute("UPDATE observations SET rapport_fr=? WHERE id=?",
                          (translated, obs_id))
                c.commit(); c.close()
            except: pass
        return translated
    except urlerr.HTTPError as e:
        if getattr(e, "code", None) == 429:
            prompt_tr = (
                "Traduis ce texte astronomique en français fluide et naturel. "
                "Réponds UNIQUEMENT avec la traduction, sans guillemets ni commentaires.\n\n"
                + text[:1500]
            )
            # 1. Essayer la rotation de clés Gemini
            try:
                result, err = _call_gemini(prompt_tr)
                if result and result != text:
                    TRANSLATE_CACHE[cache_key] = {"value": result, "ts": time.time()}
                    return result
            except Exception:
                pass
            # 2. Fallback Groq si Gemini épuisé
            try:
                groq_result, groq_err = _call_groq(
                    "Traduis en français astronomique naturel. Réponds UNIQUEMENT avec la traduction.\n\n"
                    + text[:1500]
                )
                if groq_result and groq_result != text:
                    TRANSLATE_CACHE[cache_key] = {"value": groq_result, "ts": time.time()}
                    return groq_result
            except Exception:
                pass
            return text
        log.warning(f"[translate] {e}")
        return text
    except Exception as e:
        log.warning(f"[translate] {e}")
        return text

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

def _client_ip_from_request(req):
    ip = req.headers.get("X-Forwarded-For", req.remote_addr or "")
    ip = (ip or "").split(",")[0].strip()
    return ip


# ── Owner IPs : cache in-memory rechargé toutes les 5 min ───────────────────
_OWNER_IPS_CACHE: set = set()
_OWNER_IPS_CACHE_TS: float = 0.0
_OWNER_IPS_LOCK = threading.Lock()


def _load_owner_ips() -> set:
    """Charge les IPs propriétaire depuis : env ASTROSCAN_OWNER_IPS + table owner_ips DB.
    Cache 5 min en mémoire pour éviter une requête DB à chaque requête HTTP."""
    global _OWNER_IPS_CACHE, _OWNER_IPS_CACHE_TS
    now = time.time()
    with _OWNER_IPS_LOCK:
        if now - _OWNER_IPS_CACHE_TS < 300 and _OWNER_IPS_CACHE:
            return set(_OWNER_IPS_CACHE)
        ips: set = set()
        # Depuis .env
        for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(","):
            x = x.strip()
            if x:
                ips.add(x)
        single = (os.environ.get("ASTROSCAN_MY_IP") or "").strip()
        if single:
            ips.add(single)
        # Depuis la table DB
        try:
            conn = _get_db_visitors()
            rows = conn.execute("SELECT ip FROM owner_ips").fetchall()
            conn.close()
            for r in rows:
                if r[0]:
                    ips.add(str(r[0]).strip())
        except Exception:
            pass
        _OWNER_IPS_CACHE = ips
        _OWNER_IPS_CACHE_TS = now
        return set(ips)


def _is_owner_ip(ip: str) -> bool:
    """Retourne True si l'IP appartient au propriétaire."""
    if not ip:
        return False
    return ip in _load_owner_ips()


def _invalidate_owner_ips_cache():
    """Force le rechargement du cache IPs propriétaire au prochain appel."""
    global _OWNER_IPS_CACHE_TS
    with _OWNER_IPS_LOCK:
        _OWNER_IPS_CACHE_TS = 0.0


def _compute_human_score(ua: str, page_count: int = 1, session_sec: int = 0,
                          referrer: str = "", js_beacon: bool = False) -> int:
    """Score humain 0-100 pour un visiteur.
    - UA bot connu → 0
    - UA vide ou générique → 20
    - Navigation multi-pages → +30
    - Temps sur site > 30s → +20
    - Référent valide → +10
    - JS beacon reçu → +20
    Score ≥ 60 = humain probable."""
    ua_clean = (ua or "").strip()
    if _is_bot_user_agent(ua_clean):
        return 0
    score = 20  # Base : UA non-bot
    if not ua_clean:
        score = 5
    elif len(ua_clean) < 15:
        score = 10
    if page_count > 1:
        score += 30
    if session_sec > 30:
        score += 20
    if referrer and referrer not in ("", "direct") and not referrer.startswith("https://astroscan.space"):
        score += 10
    if js_beacon:
        score += 20
    return min(100, score)


def _register_unique_visit_from_request(path_override=None):
    """Insère 1 visite par session (IP+session_id), page_views pour chaque vue de page.
    - Détecte is_owner, calcule human_score initial
    - ISP + lat/lon stockés depuis ip-api.com
    - INSERT OR IGNORE + UNIQUE INDEX = résistance totale race condition multi-workers."""
    try:
        ip = _client_ip_from_request(request)
        if ip in ("", "0.0.0.0", "127.0.0.1", "::1"):
            return False
        ua = (request.headers.get("User-Agent") or "")[:200]
        sid = (
            getattr(g, "_astroscan_sid", None)
            or request.cookies.get("astroscan_sid")
            or secrets.token_urlsafe(16)
        )[:128]
        path = (path_override or request.path or "/")[:500]
        referrer = (request.headers.get("Referer") or "")[:500]
        is_bot = 1 if _is_bot_user_agent(ua) else 0
        is_owner = 1 if _is_owner_ip(ip) else 0

        conn = _get_db_visitors()
        cur = conn.cursor()

        # ── 1. Enregistrement page_views (chaque vue, y compris bots) ────────
        try:
            cur.execute(
                "INSERT INTO page_views (session_id, ip, path, referrer) VALUES (?, ?, ?, ?)",
                (sid, ip, path, referrer),
            )
        except Exception:
            pass

        # ── 2. Une seule entrée visitor_log par (ip, session_id) ─────────────
        exists = cur.execute(
            "SELECT 1 FROM visitor_log WHERE ip = ? AND session_id = ? LIMIT 1",
            (ip, sid),
        ).fetchone()
        if exists:
            # Session connue : mettre à jour human_score si nécessaire
            try:
                page_cnt = cur.execute(
                    "SELECT COUNT(*) FROM page_views WHERE session_id=? AND ip=?",
                    (sid, ip),
                ).fetchone()[0]
                score = _compute_human_score(ua, page_count=page_cnt, referrer=referrer)
                cur.execute(
                    "UPDATE visitor_log SET human_score=? WHERE ip=? AND session_id=?",
                    (score, ip, sid),
                )
            except Exception:
                pass
            conn.commit()
            conn.close()
            return False

        # Nouveau visiteur / nouvelle session — récupérer la géoloc
        if is_bot:
            geo = {}
        else:
            geo = get_geo_from_ip(ip)
        country = (geo.get("country") or "Inconnu")[:80]
        country_code = (geo.get("country_code") or "XX")[:8]
        city = (geo.get("city") or "Inconnu")[:120]
        region = (geo.get("region") or "Inconnu")[:120]
        isp = (geo.get("isp") or "")[:200]
        lat = geo.get("lat")
        lon = geo.get("lon")
        score = _compute_human_score(ua, page_count=1, referrer=referrer)

        # INSERT OR IGNORE : sécurité race condition
        cur.execute(
            """
            INSERT OR IGNORE INTO visitor_log (
                ip, user_agent, path, session_id,
                country, country_code, city, region, flag,
                is_bot, is_owner, isp, lat, lon, human_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ip, ua, path, sid,
             country, country_code, city, region, country_code,
             is_bot, is_owner, isp, lat, lon, score),
        )
        if cur.rowcount > 0 and not is_bot and not is_owner:
            cur.execute("UPDATE visits SET count = count + 1 WHERE id=1")
        conn.commit()
        conn.close()
        return cur.rowcount > 0
    except Exception as e:
        log.warning("register unique visit: %s", e)
        return False


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

# MIGRATED TO i18n_bp 2026-05-02 (B-RECYCLE R1) — see app/blueprints/i18n/__init__.py
# @app.route("/set-lang/<lang>")
# def set_lang(lang):
#     """Enregistre la préférence de langue dans un cookie 1 an."""
#     if lang not in SUPPORTED_LANGS:
#         lang = "fr"
#     resp = make_response(redirect(request.referrer or "/portail"))
#     resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
#     return resp

# MIGRATED TO main_bp 2026-05-02 (B-RECYCLE R3) — see app/blueprints/main/__init__.py
# @app.route("/en/portail")
# @app.route("/en/")
# @app.route("/en")
# def portail_en():
#     """Version anglaise du portail — pose le cookie lang=en."""
#     resp = make_response(render_template("portail.html", lang="en"))
#     resp.set_cookie("lang", "en", max_age=60 * 60 * 24 * 365, samesite="Lax")
#     resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
#     resp.headers["Pragma"] = "no-cache"
#     resp.headers["Expires"] = "0"
#     return resp

# ─── EXPORT DONNÉES PUBLIQUES ────────────────────────────────────────────────
import csv as _csv, io as _io

@app.route("/api/export/visitors.csv")
def export_visitors_csv():
    """Export CSV statistiques visiteurs par pays — données anonymisées."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT country, country_code, COUNT(*) as visits,
                   DATE(MIN(visited_at)) as first_visit,
                   DATE(MAX(visited_at)) as last_visit
            FROM visitor_log
            WHERE country IS NOT NULL AND country != ''
              AND country NOT IN ('Unknown','Inconnu')
              AND (country_code IS NULL OR country_code != 'XX')
              AND is_bot = 0
            GROUP BY country, country_code
            ORDER BY visits DESC
        """).fetchall()
        conn.close()
        out = _io.StringIO()
        writer = _csv.writer(out)
        writer.writerow(['country', 'country_code', 'visits', 'first_visit', 'last_visit'])
        writer.writerows(rows)
        return Response(out.getvalue(), mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=astroscan_visitors.csv',
                                 'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/visitors.json")
def export_visitors_json():
    """Export JSON statistiques visiteurs par pays avec métadonnées de citation."""
    try:
        import datetime as _dt, json as _json
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT country, country_code, COUNT(*) as visits,
                   DATE(MIN(visited_at)) as first_visit,
                   DATE(MAX(visited_at)) as last_visit
            FROM visitor_log
            WHERE country IS NOT NULL AND country != ''
              AND country NOT IN ('Unknown','Inconnu')
              AND (country_code IS NULL OR country_code != 'XX')
              AND is_bot = 0
            GROUP BY country, country_code
            ORDER BY visits DESC
        """).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM visitor_log WHERE is_bot=0").fetchone()[0]
        conn.close()
        data = {
            "metadata": {
                "source": "AstroScan-Chohra", "url": "https://astroscan.space",
                "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
                "total_human_visits": total,
                "description": "Aggregated visitor stats by country — anonymized, no personal data",
                "license": "CC BY 4.0 — Scientific and educational use"
            },
            "data": [{"country": r[0], "country_code": r[1], "visits": r[2],
                      "first_visit": r[3], "last_visit": r[4]} for r in rows]
        }
        return Response(_json.dumps(data, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/ephemerides.json")
def export_ephemerides_json():
    """Export JSON éphémérides Tlemcen avec métadonnées scientifiques."""
    try:
        import datetime as _dt, json as _json
        cached = cache_get('eph_tlemcen', 300) or {}
        export = {
            "metadata": {
                "source": "AstroScan-Chohra", "location": "Tlemcen, Algeria",
                "coordinates": {"lat": 34.8753, "lon": 1.3167, "alt_m": 800},
                "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
                "license": "CC BY 4.0 — Scientific use",
                "url": "https://astroscan.space/api/export/ephemerides.json",
                "computation": "astropy 7.2 + SGP4"
            }
        }
        export.update(cached)
        return Response(_json.dumps(export, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/observations.json")
def export_observations_json():
    """Export JSON observations stellaires archivées (1500+ entrées avec analyse IA)."""
    try:
        import datetime as _dt, json as _json
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT id, timestamp, source, objets_detectes, anomalie,
                   score_confiance, analyse_gemini
            FROM observations ORDER BY timestamp DESC LIMIT 500
        """).fetchall()
        conn.close()
        data = {
            "metadata": {
                "source": "AstroScan-Chohra — Stellar Archive", "url": "https://astroscan.space",
                "count": len(rows), "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
                "license": "CC BY 4.0",
                "description": "Astronomical observations with AI analysis (Claude/Gemini)"
            },
            "data": [{"id": r[0], "timestamp": r[1], "source": r[2], "objects_detected": r[3],
                      "anomaly": r[4], "confidence_score": r[5], "ai_analysis": r[6]} for r in rows]
        }
        return Response(_json.dumps(data, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/apod-history.json")
def export_apod_history_json():
    """Export JSON historique APOD depuis le cache local."""
    try:
        import datetime as _dt, json as _json
        cache_path = f"{STATION}/data/apod_cache.json"
        with open(cache_path) as f:
            apod_cache = _json.load(f)
        data = {
            "metadata": {
                "source": "AstroScan-Chohra — NASA APOD cache", "url": "https://astroscan.space",
                "count": len(apod_cache), "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
                "license": "NASA Open Data + AstroScan FR translations CC BY 4.0"
            },
            "data": apod_cache
        }
        return Response(_json.dumps(data, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# MIGRATED TO main_bp 2026-05-02 (B-RECYCLE R3) — see app/blueprints/main/__init__.py
# @app.route("/data")
# def page_data():
#     """Open Data Portal — AstroScan-Chohra."""
#     return render_template("data_export.html")

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

# MIGRATED TO api_bp 2026-05-02 (B-RECYCLE R2) — see app/blueprints/api/__init__.py
# @app.route("/api/docs")
# def api_docs():
#     """Page documentation API publique — Swagger UI."""
#     return render_template("api_docs.html")

# MIGRATED TO api_bp 2026-05-02 (B-RECYCLE R2) — see app/blueprints/api/__init__.py
# @app.route("/api/spec.json")
# def api_spec_json():
#     """Spécification OpenAPI 3.0 en JSON."""
#     return jsonify(API_SPEC)

# ────────────────────────────────────────────────────────────────────────────

@app.route('/api/visits', methods=['GET'])
def api_visits_get():
    """Retourne le nombre actuel de visites."""
    try:
        count = _get_visits_count()
        return jsonify({'count': count})
    except Exception as e:
        log.warning(f"api/visits: {e}")
        return jsonify({'count': 0})


@app.route("/api/version")
def api_version():
    return jsonify({
        "ok": True,
        "name": "AstroScan",
        "version": "1.0.0",
        "status": "production-ready",
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route("/api/modules-status")
def api_modules_status():
    try:
        return jsonify({
            "ok": True,
            "modules": {
                "iss": True,
                "orbit": True,
                "dsn": True,
                "aurores": True,
                "apod": True,
                "aegis": True,
                "passages": True,
                "weather": True,
                "oracle": True
            }
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/ready", methods=["GET"])
def ready():
    """Indique si le worker a fini de charger l'app (éviter /status trop tôt après restart)."""
    try:
        return jsonify({"ready": bool(server_ready)})
    except Exception:
        return jsonify({"ready": False})


@app.route('/health', methods=['GET'])
def health_check():
    """
    Liveness enrichi : uptime, mémoire, disque, circuit-breakers, APIs actives.
    Pas d'appel externe (include_external=False) pour réponse rapide.
    """
    import psutil, shutil
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        d = _build_status_payload_dict(now_iso, include_external=False)
        uptime_seconds = int(d.get("uptime_seconds") or 0)
        production_mode = d.get("production_mode")
        tle_backend = d.get("tle_backend_status")
        data_freshness = d.get("data_freshness")
        tle_count = d.get("tle_count")
        overall_status = d.get("status") or "ok"
    except Exception as ex:
        log.warning("health_check: %s", ex)
        uptime_seconds = int(time.time() - START_TIME)
        production_mode = "OFFLINE"
        tle_backend = None
        data_freshness = "unknown"
        tle_count = 0
        overall_status = "degraded"

    # Mémoire process
    try:
        proc = psutil.Process()
        mem_mb = round(proc.memory_info().rss / 1024 / 1024, 1)
        mem_pct = round(psutil.virtual_memory().percent, 1)
        memory_usage = {"process_mb": mem_mb, "system_pct": mem_pct}
    except Exception:
        memory_usage = {}

    # Disque
    try:
        disk = shutil.disk_usage("/")
        disk_usage = {
            "total_gb": round(disk.total / 1e9, 1),
            "used_gb":  round(disk.used  / 1e9, 1),
            "free_gb":  round(disk.free  / 1e9, 1),
            "pct":      round(disk.used / disk.total * 100, 1),
        }
    except Exception:
        disk_usage = {}

    # Circuit-breakers : état des APIs externes
    try:
        cb_statuses = _cb_all_status()
        active_apis = {
            s["name"]: s["state"]
            for s in cb_statuses
        }
        open_count = sum(1 for s in cb_statuses if s["state"] == "OPEN")
        if open_count > 0 and overall_status == "ok":
            overall_status = "degraded"
    except Exception:
        active_apis = {}

    return jsonify({
        "status":        overall_status,
        "service":       "astroscan",
        "uptime":        uptime_seconds,
        "uptime_sec":    uptime_seconds,
        "mode":          production_mode,
        "tle_status":    tle_backend,
        "data_freshness": data_freshness,
        "tle_count":     tle_count,
        "memory_usage":  memory_usage,
        "disk_usage":    disk_usage,
        "active_apis":   active_apis,
        "timestamp":     now_iso,
    })


@app.route("/selftest", methods=["GET"])
def selftest():
    """Auto-contrôle structurel (clés fusion) — JSON toujours valide."""
    try:
        status = get_status_data()
        validation = validate_system_state(status)
        return jsonify(
            {
                "selftest": "ok" if validation["valid"] else "fail",
                "details": validation,
            }
        )
    except Exception as e:
        log.warning("selftest: %s", e)
        try:
            struct_log(
                logging.ERROR,
                category="validation",
                event="selftest_exception",
                error=str(e)[:400],
            )
        except Exception:
            pass
        return jsonify(
            {
                "selftest": "fail",
                "error": str(e),
                "details": {"valid": False, "errors": ["selftest_exception"]},
            }
        )


@app.route('/api/visits/increment', methods=['POST'])
def api_visits_increment():
    """Incrémente le compteur et retourne la nouvelle valeur."""
    try:
        count = _increment_visits()
        return jsonify({'count': count})
    except Exception as e:
        log.warning(f"api/visits/increment: {e}")
        return jsonify({'count': _get_visits_count()})


@app.route('/api/tle/status', methods=['GET'])
def api_tle_status():
    """Retourne l'état actuel du cache TLE connecté/caché/simulation."""
    try:
        return jsonify({
            "status": TLE_CACHE.get("status"),
            "source": TLE_CACHE.get("source"),
            "last_refresh_iso": TLE_CACHE.get("last_refresh_iso"),
            "count": TLE_CACHE.get("count"),
            "error": TLE_CACHE.get("error"),
        })
    except Exception as e:
        log.warning(f"/api/tle/status: {e}")
        return jsonify({
            "status": "error",
            "source": None,
            "last_refresh_iso": None,
            "count": 0,
            "error": str(e),
        })


@app.route('/api/tle/active', methods=['GET'])
def api_tle_active():
    """Retourne les TLE actifs depuis le cache connecté/disque/simulation."""
    try:
        return jsonify({
            "status": TLE_CACHE.get("status"),
            "source": TLE_CACHE.get("source"),
            "last_refresh_iso": TLE_CACHE.get("last_refresh_iso"),
            "count": TLE_CACHE.get("count"),
            "items": TLE_CACHE.get("items") or [],
            "error": TLE_CACHE.get("error"),
        })
    except Exception as e:
        log.warning(f"/api/tle/active: {e}")
        return jsonify({
            "status": "error",
            "source": None,
            "last_refresh_iso": None,
            "count": 0,
            "items": [],
            "error": str(e),
        })


@app.route('/api/tle/refresh', methods=['POST'])
def api_tle_refresh():
    """
    Déclenche un rafraîchissement manuel des TLE.
    Usage prévu : debug / appel local (aucun secret exposé).
    """
    try:
        ok = fetch_tle_from_celestrak()
        return jsonify({
            "ok": bool(ok),
            "status": TLE_CACHE.get("status"),
            "count": TLE_CACHE.get("count"),
            "last_refresh_iso": TLE_CACHE.get("last_refresh_iso"),
            "error": TLE_CACHE.get("error"),
        })
    except Exception as e:
        log.warning(f"/api/tle/refresh: {e}")
        return jsonify({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════
# PAGES
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template(
        'landing.html',
        seo_title=SEO_HOME_TITLE,
        seo_description=SEO_HOME_DESCRIPTION,
    )

@app.route('/portail')
def portail():
    response = make_response(render_template('portail.html', lang=get_user_lang()))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/landing')
def landing_page():
    """Landing marketing AstroScan-Chohra (template existant) — liens et redirection vers /portail."""
    return render_template(
        'landing.html',
        seo_title=SEO_HOME_TITLE,
        seo_description=SEO_HOME_DESCRIPTION,
    )


@app.route('/technical')
def technical_page():
    return render_template('technical.html')


@app.route('/dashboard')
def dashboard():
    return render_template('research_dashboard.html')


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


def get_geo_from_ip(ip):
    """Géolocalisation complète via ip-api.com (cache 24 h) : pays, ville, région, ISP, lat/lon.
    Retourne {} si IP invalide ou échec. Fallback ipinfo.io si ip-api échoue."""
    if ip is None:
        return {}
    ip = str(ip).strip()
    if ip in ("", "—", "127.0.0.1", "::1"):
        return {"country": "Serveur local", "city": "Serveur local", "country_code": "LO", "isp": "localhost"}
    ip = ip.split(",")[0].strip()
    if not ip:
        return {}
    cache_key = f"geo_ip:{ip}"
    cached = cache_get(cache_key, 86400)
    if cached is not None:
        return cached
    out = {}
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,regionName,lat,lon,isp",
            timeout=3,
        )
        d = r.json()
        if d.get("status") == "success":
            out = {
                "country": d.get("country") or "Inconnu",
                "city": d.get("city") or "Inconnu",
                "country_code": (d.get("countryCode") or "XX").upper(),
                "region": d.get("regionName") or "Inconnu",
                "lat": d.get("lat"),
                "lon": d.get("lon"),
                "isp": d.get("isp") or "",
            }
    except Exception:
        pass
    if not out:
        # Fallback ipinfo.io si ip-api échoue ou rate-limit
        try:
            r2 = requests.get(f"https://ipinfo.io/{ip}/json", timeout=3)
            d2 = r2.json() if r2.ok else {}
            cc = (d2.get("country") or "").strip().upper()
            loc = (d2.get("loc") or "").split(",")
            out = {
                "country": d2.get("country_name") or d2.get("country") or "Inconnu",
                "city": d2.get("city") or "Inconnu",
                "country_code": cc or "XX",
                "region": d2.get("region") or "Inconnu",
                "lat": float(loc[0]) if len(loc) == 2 else None,
                "lon": float(loc[1]) if len(loc) == 2 else None,
                "isp": d2.get("org") or "",
            }
        except Exception:
            out = {}
    cache_set(cache_key, out)
    return out


def _analytics_empty_payload():
    return {
        "total_visits": 0,
        "unique_ips": 0,
        "total_tracked_events": 0,
        "last_activity": "—",
        "top_countries": [],
        "top_cities": [],
        "latest_visits": [],
        "top_pages_by_time": [],
        "avg_duration_by_page": [],
        "longest_sessions": [],
        "session_visitors_detail": [],
        "sessions_timeline": [],
        "bot_count": 0,
    }


def _load_analytics_readonly():
    """Lecture seule SQLite (visitor_log, session_time). Jamais de levée vers l'utilisateur."""
    out = _analytics_empty_payload()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        last_candidates = []

        if "visitor_log" in tables:
            r = cur.execute("SELECT COUNT(*) AS c FROM visitor_log").fetchone()
            out["total_visits"] = int(r["c"] if r else 0)
            r = cur.execute(
                "SELECT COUNT(DISTINCT ip) AS c FROM visitor_log "
                "WHERE ip NOT IN ('127.0.0.1', '::1')"
            ).fetchone()
            out["unique_ips"] = int(r["c"] if r else 0)
            out["top_countries"] = [
                {"country": row[0], "code": row[1] or "", "count": row[2]}
                for row in cur.execute(
                    "SELECT country, country_code, COUNT(*) AS cnt FROM visitor_log "
                    "WHERE country != 'Unknown' GROUP BY country "
                    "ORDER BY cnt DESC LIMIT 15"
                ).fetchall()
            ]
            out["top_cities"] = [
                {"country": row[0], "city": row[1], "count": row[2]}
                for row in cur.execute(
                    "SELECT country, city, COUNT(*) AS cnt FROM visitor_log "
                    "WHERE ip NOT IN ('127.0.0.1', '::1') "
                    "GROUP BY country, city ORDER BY cnt DESC LIMIT 15"
                ).fetchall()
            ]
            out["latest_visits"] = [
                {
                    "ip": row["ip"],
                    "country": row["country"],
                    "city": row["city"],
                    "path": row["path"],
                    "visited_at": row["visited_at"],
                }
                for row in cur.execute(
                    "SELECT ip, country, city, path, visited_at "
                    "FROM visitor_log ORDER BY id DESC LIMIT 10"
                )
            ]
            m = cur.execute("SELECT MAX(visited_at) AS m FROM visitor_log").fetchone()
            if m and m["m"]:
                last_candidates.append(str(m["m"]))

        if "session_time" in tables:
            r = cur.execute("SELECT COUNT(*) AS c FROM session_time").fetchone()
            out["total_tracked_events"] = int(r["c"] if r else 0)
            out["top_pages_by_time"] = [
                {"path": row[0] or "", "total_seconds": int(row[1] or 0)}
                for row in cur.execute(
                    "SELECT path, COALESCE(SUM(duration), 0) AS s FROM session_time "
                    "GROUP BY path ORDER BY s DESC LIMIT 15"
                ).fetchall()
            ]
            out["avg_duration_by_page"] = [
                {"path": row[0] or "", "avg_seconds": round(float(row[1] or 0), 2)}
                for row in cur.execute(
                    "SELECT path, AVG(duration) AS a FROM session_time "
                    "GROUP BY path ORDER BY a DESC LIMIT 15"
                ).fetchall()
            ]
            out["longest_sessions"] = [
                {
                    "session_id": row["session_id"] or "",
                    "path": row["path"] or "",
                    "duration": int(row["duration"] or 0),
                    "created_at": row["created_at"] or "",
                }
                for row in cur.execute(
                    "SELECT session_id, path, duration, created_at FROM session_time "
                    "ORDER BY duration DESC LIMIT 10"
                )
            ]
            out["session_visitors_detail"] = []
            try:
                if "visitor_log" in tables:
                    detail_rows = cur.execute(
                        """
                        SELECT
                          st.session_id AS sid,
                          COALESCE(SUM(st.duration), 0) AS total_time,
                          COUNT(*) AS pages_count,
                          GROUP_CONCAT(st.path ORDER BY st.created_at) AS journey,
                          MIN(st.created_at) AS start_time,
                          MAX(st.created_at) AS end_time,
                          (SELECT country FROM visitor_log v
                           WHERE v.session_id = st.session_id
                           ORDER BY v.id DESC LIMIT 1) AS country,
                          (SELECT city FROM visitor_log v
                           WHERE v.session_id = st.session_id
                           ORDER BY v.id DESC LIMIT 1) AS city,
                          (SELECT country_code FROM visitor_log v
                           WHERE v.session_id = st.session_id
                           ORDER BY v.id DESC LIMIT 1) AS country_code
                        FROM session_time st
                        WHERE st.session_id IS NOT NULL AND TRIM(st.session_id) != ''
                        GROUP BY st.session_id
                        ORDER BY COALESCE(SUM(st.duration), 0) DESC
                        LIMIT 20
                        """
                    ).fetchall()
                else:
                    detail_rows = cur.execute(
                        """
                        SELECT
                          st.session_id AS sid,
                          COALESCE(SUM(st.duration), 0) AS total_time,
                          COUNT(*) AS pages_count,
                          GROUP_CONCAT(st.path ORDER BY st.created_at) AS journey,
                          MIN(st.created_at) AS start_time,
                          MAX(st.created_at) AS end_time,
                          NULL AS country,
                          NULL AS city,
                          NULL AS country_code
                        FROM session_time st
                        WHERE st.session_id IS NOT NULL AND TRIM(st.session_id) != ''
                        GROUP BY st.session_id
                        ORDER BY COALESCE(SUM(st.duration), 0) DESC
                        LIMIT 20
                        """
                    ).fetchall()
                for dr in detail_rows:
                    cc = dr["country_code"] if dr["country_code"] is not None else ""
                    st_iso = dr["start_time"]
                    out["session_visitors_detail"].append(
                        {
                            "session_id": dr["sid"] or "",
                            "country": dr["country"] or "—",
                            "city": dr["city"] or "—",
                            "total_time_fmt": _analytics_fmt_duration_sec(dr["total_time"]),
                            "pages_count": int(dr["pages_count"] or 0),
                            "journey": _analytics_journey_display(dr["journey"]),
                            "start_time": st_iso or "—",
                            "end_time": dr["end_time"] or "—",
                            "start_local": _analytics_start_local_display(st_iso, cc),
                        }
                    )
            except Exception:
                out["session_visitors_detail"] = []
            out["sessions_timeline"] = []
            try:
                t_rows = cur.execute(
                    "SELECT session_id, path, duration, created_at FROM session_time "
                    "WHERE session_id IS NOT NULL AND TRIM(session_id) != '' "
                    "ORDER BY session_id ASC, created_at ASC"
                ).fetchall()
                sessions_detail = {}
                for tr in t_rows:
                    sid = tr["session_id"]
                    if sid not in sessions_detail:
                        sessions_detail[sid] = {"events": []}
                    sessions_detail[sid]["events"].append(
                        {
                            "path": tr["path"] or "",
                            "duration": tr["duration"],
                            "time": tr["created_at"],
                        }
                    )
                if sessions_detail:
                    sids_ordered = sorted(
                        sessions_detail.keys(),
                        key=lambda s: max(
                            str(e["time"]) for e in sessions_detail[s]["events"]
                        ),
                        reverse=True,
                    )[:10]
                    for sid in sids_ordered:
                        country = city = ip = ua = ""
                        cc = ""
                        if "visitor_log" in tables:
                            gr = cur.execute(
                                "SELECT country, city, country_code, ip, user_agent "
                                "FROM visitor_log "
                                "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                                (sid,),
                            ).fetchone()
                            if gr:
                                country = gr["country"] or ""
                                city = gr["city"] or ""
                                cc = gr["country_code"] or ""
                                ip = gr["ip"] or ""
                                _ua = gr["user_agent"] or ""
                                ua = (
                                    _ua
                                    if len(_ua) <= 220
                                    else _ua[:217] + "..."
                                )
                        evlist = sessions_detail[sid]["events"]
                        first_t = min(str(e["time"]) for e in evlist)
                        total_time = 0
                        for e in evlist:
                            try:
                                total_time += int(e["duration"] or 0)
                            except Exception:
                                pass
                        n_events = len(evlist)
                        seen_paths = set()
                        modules = []
                        for e in evlist:
                            p = (e["path"] or "").strip()
                            if p and p not in seen_paths:
                                seen_paths.add(p)
                                modules.append(p)
                        sess = {
                            "session_id": sid,
                            "country": country or "—",
                            "city": city or "—",
                            "ip": ip or "—",
                            "ua": ua or "—",
                            "total_time": total_time,
                            "total_time_fmt": _analytics_fmt_duration_sec(
                                total_time
                            ),
                            "classification": _analytics_session_classification(
                                total_time, n_events
                            ),
                            "modules": modules,
                            "start_local": _analytics_start_local_display(
                                first_t, cc
                            ),
                            "events": [
                                {
                                    "time_local": _analytics_time_hms_local(
                                        e["time"], cc
                                    ),
                                    "path": e["path"],
                                    "duration_fmt": _analytics_fmt_duration_sec(
                                        e["duration"]
                                    ),
                                }
                                for e in evlist
                            ],
                        }
                        ip = sess.get("ip")
                        geo = get_geo_from_ip(ip)
                        sess["country"] = geo.get("country")
                        sess["city"] = geo.get("city")
                        if not sess.get("country"):
                            sess["country"] = country or "—"
                        if not sess.get("city"):
                            sess["city"] = city or "—"
                        visit_count = len(sess["events"])
                        modules_str = ", ".join(sess["modules"][:4])
                        if len(sess["modules"]) > 4:
                            modules_str += "..."
                        sess["summary_line"] = (
                            f"🌍 {sess.get('country', '—')} - {sess.get('city', '—')} | "
                            f"🕒 {sess.get('start_local', '—')} | "
                            f"👁 {visit_count} visites | "
                            f"⏱ {sess.get('total_time_fmt', '—')} | "
                            f"📊 {modules_str if modules_str else '—'}"
                        )
                        out["sessions_timeline"].append(sess)
            except Exception:
                out["sessions_timeline"] = []
            m = cur.execute("SELECT MAX(created_at) AS m FROM session_time").fetchone()
            if m and m["m"]:
                last_candidates.append(str(m["m"]))

        if last_candidates:
            out["last_activity"] = max(last_candidates)

        conn.close()
    except Exception:
        return _analytics_empty_payload()
    return out


@app.route("/analytics")
def analytics_dashboard():
    """Dashboard analytics complet : sessions, page_views, human_score, owner IPs."""
    try:
        data = _load_analytics_readonly()
    except Exception:
        data = _analytics_empty_payload()

    # ── Données complémentaires issues des nouvelles tables ──────────────────
    total_page_views = 0
    human_count = 0
    suspect_count = 0
    top_pages = []
    owner_visits = []
    db_ips = []
    env_ips = [x.strip() for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(",") if x.strip()]
    avg_human_score = 0.0
    try:
        conn = _get_db_visitors()
        conn.row_factory = sqlite3.Row

        total_page_views = (conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0] or 0)

        # Scoring répartition
        human_count = (conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_bot=0 AND is_owner=0 AND human_score >= 60"
        ).fetchone()[0] or 0)
        suspect_count = (conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_bot=0 AND is_owner=0 AND human_score >= 20 AND human_score < 60"
        ).fetchone()[0] or 0)
        avg_row = conn.execute(
            "SELECT ROUND(AVG(human_score),1) FROM visitor_log WHERE is_bot=0 AND is_owner=0 AND human_score >= 0"
        ).fetchone()
        avg_human_score = float(avg_row[0] or 0)

        # Top 10 pages
        top_page_rows = conn.execute(
            "SELECT path, COUNT(*) as cnt FROM page_views WHERE path NOT LIKE '/static%' "
            "GROUP BY path ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        top_pages = [{"path": r["path"], "count": r["cnt"]} for r in top_page_rows]

        # Visites owner
        ov_rows = conn.execute(
            "SELECT ip, COALESCE(country,'?') as country, COALESCE(city,'?') as city, "
            "COALESCE(isp,'') as isp, MAX(visited_at) as last_visit, COUNT(*) as sessions "
            "FROM visitor_log WHERE is_owner=1 GROUP BY ip ORDER BY last_visit DESC LIMIT 20"
        ).fetchall()
        owner_visits = [dict(r) for r in ov_rows]

        # Top villes enrichies (avec ISP)
        city_rows = conn.execute(
            "SELECT country, city, COALESCE(region,'') as region, "
            "COALESCE(isp,'') as isp, COUNT(*) as cnt "
            "FROM visitor_log WHERE is_bot=0 AND is_owner=0 "
            "AND city != 'Unknown' AND city != '' "
            "GROUP BY city ORDER BY cnt DESC LIMIT 15"
        ).fetchall()
        data["top_cities"] = [
            {"country": r["country"], "city": r["city"], "region": r["region"],
             "isp": r["isp"], "count": r["cnt"]}
            for r in city_rows
        ]

        # Dernières visites enrichies (avec human_score + ISP)
        last_rows = conn.execute(
            "SELECT ip, country, city, path, visited_at, isp, human_score, is_bot, is_owner "
            "FROM visitor_log ORDER BY id DESC LIMIT 30"
        ).fetchall()
        data["latest_visits"] = [dict(r) for r in last_rows]

        # ISP dans sessions_timeline
        for block in data.get("sessions_timeline", []):
            try:
                ip = block.get("ip", "")
                if ip:
                    vrow = conn.execute(
                        "SELECT isp, human_score FROM visitor_log WHERE ip=? LIMIT 1", (ip,)
                    ).fetchone()
                    block["isp"] = vrow["isp"] if vrow else ""
                    block["human_score"] = int(vrow["human_score"] or -1) if vrow else -1
                else:
                    block["isp"] = ""
                    block["human_score"] = -1
            except Exception:
                block["isp"] = ""
                block["human_score"] = -1

        # Owner IPs depuis DB
        db_ip_rows = conn.execute(
            "SELECT id, ip, label, added_at FROM owner_ips ORDER BY added_at DESC"
        ).fetchall()
        db_ips = [dict(r) for r in db_ip_rows]

        conn.close()
    except Exception as ex:
        log.warning("analytics_dashboard extra: %s", ex)

    bot_count = data.get("bot_count", 0)
    if not bot_count:
        try:
            conn2 = _get_db_visitors()
            bot_count = (conn2.execute("SELECT COUNT(*) FROM visitor_log WHERE is_bot=1").fetchone()[0] or 0)
            conn2.close()
        except Exception:
            bot_count = 0

    return render_template(
        "analytics.html",
        # KPIs existants
        total_visits=data.get("total_visits", 0),
        unique_ips=data.get("unique_ips", 0),
        total_tracked_events=data.get("total_tracked_events", 0),
        last_activity=data.get("last_activity", "—"),
        # Nouveaux KPIs
        total_sessions=data.get("total_visits", 0),
        total_page_views=int(total_page_views),
        human_count=int(human_count),
        suspect_count=int(suspect_count),
        bot_count=int(bot_count),
        human_pct=round(100 * human_count / max(1, data.get("total_visits", 1)), 1),
        avg_human_score=round(avg_human_score, 1),
        owner_count=len(owner_visits),
        # Listes
        top_pages=top_pages,
        top_countries=data.get("top_countries", []),
        top_cities=data.get("top_cities", []),
        top_pages_by_time=data.get("top_pages_by_time", []),
        avg_duration_by_page=data.get("avg_duration_by_page", []),
        latest_visits=data.get("latest_visits", []),
        sessions_timeline=data.get("sessions_timeline", []),
        session_visitors_detail=data.get("session_visitors_detail", []),
        # Owner
        owner_visits=owner_visits,
        db_ips=db_ips,
        env_ips=env_ips,
    )


@app.route('/overlord_live')
def overlord_live():
    return render_template('overlord_live.html')

@app.route('/galerie')
def galerie():
    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anomalies = conn.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
        rows = conn.execute(
            "SELECT id, timestamp, source, objets_detectes, analyse_gemini as rapport_gemini, "
            "COALESCE(title,'') as title, anomalie "
            "FROM observations ORDER BY id DESC LIMIT 200"
        ).fetchall()
        class_rows = conn.execute(
            "SELECT COALESCE(objets_detectes,'inconnu') as type, COUNT(*) as n "
            "FROM observations GROUP BY objets_detectes ORDER BY n DESC"
        ).fetchall()
        conn.close()
        observations = [dict(r) for r in rows]
        stats = {'total': total, 'anomalies': anomalies}
        classification_stats = [dict(r) for r in class_rows]
    except Exception as e:
        log.warning(f"galerie: {e}")
        observations = []
        stats = {'total': 0, 'anomalies': 0}
        classification_stats = []
    return render_template('galerie.html', stats=stats, observations=observations, classification_stats=classification_stats)

@app.route('/observatoire')
def observatoire():
    nasa_key = os.environ.get('NASA_API_KEY', 'DEMO_KEY') or 'DEMO_KEY'
    response = make_response(render_template('observatoire.html', nasa_key=nasa_key))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# MIGRATED TO pages_bp 2026-05-02 (B-RECYCLE R2) — see app/blueprints/pages/__init__.py
# @app.route('/vision')
# def vision():
#     return render_template('vision.html')


@app.route('/vision-2026')
def vision_2026():
    return render_template('vision_2026.html')


@app.route('/sondes')
def sondes():
    """Page SONDES SPATIALES — télémetrie Voyager, Mars, ISS, JWST, Hubble, Parker."""
    return render_template('sondes.html')


@app.route('/telemetrie-sondes')
def telemetrie_sondes():
    """Télémétrie live Voyager 1&2, James Webb, New Horizons."""
    return render_template('telemetrie_sondes.html')


@app.route('/sky-camera')
def sky_camera():
    """Live Sky Camera — webcam + détection étoiles + Claude Vision."""
    return render_template('sky_camera.html')


@app.route('/api/sky-camera/analyze', methods=['POST'])
def api_sky_camera_analyze():
    """Analyse d'image ciel nocturne via Claude Vision (claude-opus-4-5)."""
    try:
        data = request.get_json(force=True) or {}
        image_b64 = data.get('image_base64', '')
        datetime_str = data.get('datetime', datetime.now(timezone.utc).strftime('%d/%m/%Y à %Hh%M'))
        stars_detected = int(data.get('stars_detected', 0))
        sim_mode = bool(data.get('sim_mode', False))

        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
        if not api_key:
            return jsonify({'ok': False, 'error': 'Clé API Anthropic non configurée', 'analyse': 'Clé API manquante.'}), 500

        mode_note = " (image de simulation)" if sim_mode else ""
        system_prompt = (
            "Tu es ORBITAL-CHOHRA, expert en astronomie et astrophysique. "
            "Tu analyses des images du ciel nocturne avec précision et poésie. "
            "Réponds toujours en français."
        )
        user_content = [
            {
                "type": "text",
                "text": (
                    f"Analyse cette image du ciel nocturne{mode_note} capturée le {datetime_str}. "
                    f"Mon algorithme de détection a identifié environ {stars_detected} points lumineux.\n\n"
                    "Identifie et liste :\n"
                    "1. Les étoiles visibles et leurs noms probables\n"
                    "2. Les constellations présentes ou suggérées\n"
                    "3. Les planètes si visibles\n"
                    "4. La magnitude approximative des objets les plus brillants\n"
                    "5. Un fait cosmique poétique sur l'objet le plus remarquable\n\n"
                    "Réponds de façon structurée mais avec un ton poétique et précis. "
                    "À la fin, fournis sur une ligne séparée au format JSON compact : "
                    '{\"stars\":N,\"magnitude\":\"X.X\",\"constellation\":\"Nom\",\"planets\":\"Nom ou Aucune\"}'
                )
            }
        ]
        if image_b64:
            user_content.insert(0, {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64
                }
            })

        headers = {
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
        body = {
            'model': 'claude-opus-4-5',
            'max_tokens': 1024,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_content}],
        }
        r = requests.post('https://api.anthropic.com/v1/messages', headers=headers, json=body, timeout=60)
        rdata = r.json()
        if r.status_code != 200:
            err = (rdata.get('error') or {}).get('message', r.text)[:300]
            return jsonify({'ok': False, 'error': err, 'analyse': f'Erreur API : {err}'}), 502

        text = rdata['content'][0]['text'].strip()

        # Extraire le JSON de stats en fin de réponse
        stars_n, magnitude, constellation, planets = stars_detected, '—', '—', '—'
        import re as _re
        m = _re.search(r'\{[^{}]*"stars"[^{}]*\}', text)
        if m:
            try:
                meta = json.loads(m.group())
                stars_n = meta.get('stars', stars_n)
                magnitude = str(meta.get('magnitude', '—'))
                constellation = str(meta.get('constellation', '—'))
                planets = str(meta.get('planets', '—'))
                # Retire le JSON brut du texte affiché
                text = text[:m.start()].strip()
            except Exception:
                pass

        return jsonify({
            'ok': True,
            'analyse': text,
            'stars_count': stars_n,
            'magnitude': magnitude,
            'constellation': constellation,
            'planets': planets,
        })
    except Exception as e:
        log.warning('api_sky_camera_analyze: %s', e)
        return jsonify({'ok': False, 'error': str(e), 'analyse': f'Erreur serveur : {e}'}), 500


@app.route('/api/sky-camera/simulate')
def api_sky_camera_simulate():
    """Retourne une image de ciel nocturne pour le mode simulation.
    Priorité : APOD NASA → image statique locale.
    """
    try:
        nasa_key = (os.environ.get('NASA_API_KEY') or 'DEMO_KEY').strip()
        apod = cache_get('apod_hd', 3600)
        if not apod:
            raw = _curl_get(f'https://api.nasa.gov/planetary/apod?api_key={nasa_key}', timeout=12)
            if raw:
                apod_data = json.loads(raw)
                if apod_data.get('media_type') == 'image':
                    url = apod_data.get('hdurl') or apod_data.get('url', '')
                    return jsonify({'ok': True, 'url': url, 'title': apod_data.get('title', ''), 'source': 'NASA APOD'})
        if apod and isinstance(apod, dict):
            inner = apod.get('apod') or apod
            url = inner.get('hdurl') or inner.get('url', '')
            if url:
                return jsonify({'ok': True, 'url': url, 'source': 'NASA APOD (cache)'})
    except Exception as e:
        log.warning('sky_simulate APOD: %s', e)
    # Fallback image NASA publique connue
    return jsonify({
        'ok': True,
        'url': 'https://apod.nasa.gov/apod/image/2401/OrionMolCloud_Addis_960.jpg',
        'title': 'Orion Molecular Cloud',
        'source': 'NASA APOD fallback'
    })


@app.route('/api/sondes/live')
def api_sondes_live():
    """Télémétrie temps réel — Voyager 1&2, James Webb, New Horizons.
    Tente NASA JPL Horizons, fallback sur calcul physique local.
    Cache 5 min pour ne pas surcharger JPL.
    """
    cached = cache_get('sondes_live', 240)
    if cached is not None:
        return jsonify(cached)

    C_KM_S = 299792.458  # vitesse lumière km/s
    now = datetime.now(timezone.utc)

    # ── Calculs physiques de référence (fallback) ──
    # Voyager 1 : lancée 5 sep 1977, ~17.03 km/s
    V1_LAUNCH = datetime(1977, 9, 5, tzinfo=timezone.utc)
    V1_SPEED  = 17.026  # km/s moyen actuel
    v1_elapsed_s = (now - V1_LAUNCH).total_seconds()
    v1_dist_km = v1_elapsed_s * V1_SPEED
    v1_dist_au = v1_dist_km / 149_597_870.7

    # Voyager 2 : lancée 20 aoû 1977, ~15.37 km/s
    V2_LAUNCH = datetime(1977, 8, 20, tzinfo=timezone.utc)
    V2_SPEED  = 15.374
    v2_elapsed_s = (now - V2_LAUNCH).total_seconds()
    v2_dist_km = v2_elapsed_s * V2_SPEED
    v2_dist_au = v2_dist_km / 149_597_870.7

    # New Horizons : lancée 19 jan 2006, ~14.0 km/s
    NH_LAUNCH = datetime(2006, 1, 19, tzinfo=timezone.utc)
    NH_SPEED  = 14.03
    nh_elapsed_s = (now - NH_LAUNCH).total_seconds()
    nh_dist_km = nh_elapsed_s * NH_SPEED
    nh_dist_au = nh_dist_km / 149_597_870.7

    # JWST : distance L2 quasi-fixe ~1,5M km, temp miroir ~-233°C
    webb_dist_km  = 1_500_000.0
    webb_temp_c   = -233.0
    webb_delay_s  = webb_dist_km / C_KM_S

    _now_iso = now.isoformat()
    _local_dq = {
        'source': 'calcul_physique_local',
        'last_update': _now_iso,
        'confidence': 0.92,
        'stale': False,
    }
    payload = {
        'ok': True,
        'timestamp': _now_iso,
        'source': 'calcul_local',
        'voyager_1': {
            'dist_km': round(v1_dist_km),
            'dist_au': round(v1_dist_au, 3),
            'speed_km_s': V1_SPEED,
            'signal_delay_s': round(v1_dist_km / C_KM_S),
            'status': 'MISSION ACTIVE — Espace interstellaire',
            'data_quality': dict(_local_dq),
        },
        'voyager_2': {
            'dist_km': round(v2_dist_km),
            'dist_au': round(v2_dist_au, 3),
            'speed_km_s': V2_SPEED,
            'signal_delay_s': round(v2_dist_km / C_KM_S),
            'status': 'MISSION ACTIVE — Espace interstellaire',
            'data_quality': dict(_local_dq),
        },
        'james_webb': {
            'dist_km': webb_dist_km,
            'position': 'Point Lagrange L2',
            'mirror_temp_c': webb_temp_c,
            'signal_delay_s': round(webb_delay_s),
            'status': 'EN OBSERVATION',
            'data_quality': {
                'source': 'ESA/NASA public data',
                'last_update': _now_iso,
                'confidence': 0.95,
                'stale': False,
            },
        },
        'new_horizons': {
            'dist_km': round(nh_dist_km),
            'dist_au': round(nh_dist_au, 3),
            'speed_km_s': NH_SPEED,
            'signal_delay_s': round(nh_dist_km / C_KM_S),
            'status': 'MODE HIBERNATION — Ceinture de Kuiper',
            'data_quality': dict(_local_dq),
        },
    }

    # ── Tentative NASA JPL Horizons pour Voyager 1&2 (cache 1h) ──
    # Sanity check : Voyager 1 > 140 AU, Voyager 2 > 110 AU, vitesses 10-25 km/s
    try:
        jpl_data = get_cached('voyager', 3600, _fetch_voyager)
        if jpl_data:
            v1j = jpl_data.get('VOYAGER_1') or jpl_data.get('voyager_1')
            if v1j and v1j.get('dist_km'):
                d_au = v1j.get('dist_au', v1j['dist_km'] / 149_597_870.7)
                spd  = v1j.get('speed_km_s', 0) or 0
                if d_au > 140 and 10 < spd < 25:
                    payload['voyager_1'].update({
                        'dist_km': v1j['dist_km'],
                        'dist_au': round(d_au, 3),
                        'speed_km_s': round(spd, 3),
                        'signal_delay_s': round(v1j['dist_km'] / C_KM_S),
                        'data_quality': v1j.get('data_quality', {
                            'source': 'NASA JPL Horizons',
                            'last_update': _now_iso,
                            'confidence': 0.999,
                            'stale': False,
                        }),
                    })
                    payload['source'] = 'NASA JPL Horizons'
            v2j = jpl_data.get('VOYAGER_2') or jpl_data.get('voyager_2')
            if v2j and v2j.get('dist_km'):
                d_au = v2j.get('dist_au', v2j['dist_km'] / 149_597_870.7)
                spd  = v2j.get('speed_km_s', 0) or 0
                if d_au > 110 and 10 < spd < 25:
                    payload['voyager_2'].update({
                        'dist_km': v2j['dist_km'],
                        'dist_au': round(d_au, 3),
                        'speed_km_s': round(spd, 3),
                        'signal_delay_s': round(v2j['dist_km'] / C_KM_S),
                        'data_quality': v2j.get('data_quality', {
                            'source': 'NASA JPL Horizons',
                            'last_update': _now_iso,
                            'confidence': 0.999,
                            'stale': False,
                        }),
                    })
    except Exception as e:
        log.warning('api_sondes_live JPL: %s', e)

    cache_set('sondes_live', payload)
    return jsonify(payload)




# MIGRATED TO pages_bp 2026-05-02 (B-RECYCLE R2) — see app/blueprints/pages/__init__.py
# @app.route('/scientific')
# def scientific():
#     return render_template('scientific.html')

# ══════════════════════════════════════════════════════════════
# API — DONNÉES PRINCIPALES
# ══════════════════════════════════════════════════════════════

@app.route('/api/latest')
def api_latest():
    lang = request.args.get('lang', 'fr').lower()
    try:
        conn = get_db()
        cur  = conn.cursor()
        total     = cur.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anomalies = cur.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
        sources   = cur.execute("SELECT COUNT(DISTINCT source) FROM observations").fetchone()[0]
        try:
            req_j = cur.execute(
                "SELECT COUNT(*) FROM observations WHERE date(timestamp)=date('now')"
            ).fetchone()[0]
        except:
            req_j = 0

        try:
            limit_arg = request.args.get('limit', '20')
            limit = min(200, max(1, int(limit_arg))) if str(limit_arg).isdigit() else 20
        except Exception:
            limit = 20

        try:
            rows = cur.execute(
                "SELECT id, timestamp, source, analyse_gemini, analyse_gemini as rapport_gemini, "
                "COALESCE(rapport_fr,'') as rapport_fr, objets_detectes, anomalie, "
                "COALESCE(title,'') as title, COALESCE(objets_detectes,'') as type_objet, "
                "COALESCE(score_confiance,0.0) as confidence "
                "FROM observations ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        except Exception:
            rows = cur.execute(
                "SELECT id, timestamp, source, analyse_gemini, analyse_gemini as rapport_gemini, "
                "'' as rapport_fr, objets_detectes, anomalie, "
                "'' as title, '' as type_objet, 0.0 as confidence "
                "FROM observations ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()

        obs_list = []
        for row in rows:
            r = dict(row)
            raw = r.get('rapport_gemini') or r.get('analyse_gemini') or ''
            if lang == 'fr':
                fr = (r.get('rapport_fr') or '').strip()
                r['rapport_gemini'] = fr if fr else raw
            else:
                r['rapport_gemini'] = raw
            r['rapport_display'] = r['rapport_gemini']
            obs_list.append(r)

        return jsonify({
            'ok': True, 'total': total, 'anomalies': anomalies,
            'sources': sources, 'telescopes': 9, 'req_jour': req_j,
            'observations': obs_list,
            'notice': 'Analyses AEGIS',
        })
    except Exception as e:
        log.error(f"api_latest: {e}")
        return jsonify({'ok': False, 'error': str(e), 'total': 0, 'observations': []})

# Cache images par source — FICHIERS séparés (évite que tout affiche la même image)
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

@app.route('/api/sync/state', methods=['GET'])
def api_sync_state_get():
    """État canonique partagé (PC + Android) : source télescope affichée."""
    return jsonify({'ok': True, 'source': _sync_state_read()})

@app.route('/api/sync/state', methods=['POST'])
def api_sync_state_post():
    """Met à jour l'état partagé (quand un client change la source)."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        source = data.get('source') or request.form.get('source') or 'live'
    except Exception:
        source = 'live'
    s = _sync_state_write(source)
    return jsonify({'ok': True, 'source': s})

@app.route('/api/telescope/sources')
def api_telescope_sources():
    """Liste des sources live sélectionnables."""
    return jsonify({
        'ok': True,
        'sources': [
            {'id': 'live', 'name': 'Flux principal', 'desc': 'Dernière image du pipeline (feeder)', 'icon': '📡'},
            {'id': 'apod', 'name': 'NASA APOD', 'desc': 'Image du jour — temps 0', 'icon': '🔭'},
            {'id': 'hubble', 'name': 'ESA Hubble', 'desc': 'Archives Hubble — temps 0', 'icon': '🌌'},
            {'id': 'apod_archive', 'name': 'NASA APOD (archive)', 'desc': 'Image aléatoire 2015–2024', 'icon': '📁'},
        ]
    })


@app.route('/api/observatory/status')
def api_observatory_status():
    """Read-only observatory connector status (JSON). Honesty-safe provider capabilities."""
    try:
        from modules.observatory.real_telescope_connector import get_observatory_status
        return jsonify(get_observatory_status())
    except Exception as e:
        log.warning('api/observatory/status: %s', e)
        return jsonify({'providers': [], 'summary': 'Observatory status unavailable.'})


@app.route('/observatory/status')
def observatory_status_page():
    """Read-only HTML view of observatory connector status."""
    try:
        from modules.observatory.real_telescope_connector import get_observatory_status
        data = get_observatory_status()
        return render_template('observatory_status.html', **data)
    except Exception as e:
        log.warning('observatory/status: %s', e)
        return render_template('observatory_status.html', providers=[], summary='Observatory status unavailable.')


@app.route('/api/telescope/live')
def api_telescope_live():
    """APOD du jour NASA : titre + description traduits en FR via Gemini.
    Lit d'abord le cache apod_meta.json (produit par nasa_feeder.py) ;
    si absent ou périmé, traduit en ligne via _gemini_translate()."""
    try:
        # ── 1. Essai depuis le cache feeder (apod_meta.json) ──────────────
        meta_path = os.path.join(STATION, 'telescope_live', 'apod_meta.json')
        today = datetime.utcnow().strftime('%Y-%m-%d')
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding='utf-8') as f:
                    meta = json.load(f)
                if meta.get('date') == today or meta.get('fetched_at', '').startswith(today):
                    analyse_claude = meta.get('analyse_claude', '')
                    # Si pas d'analyse Claude dans le cache, la générer maintenant
                    if not analyse_claude:
                        title_en = meta.get('title_original') or meta.get('title', '')
                        expl_en  = meta.get('explanation_original') or meta.get('explanation', '')
                        if title_en and expl_en:
                            prompt_analyse = (
                                f"Image astronomique NASA APOD du {meta.get('date','aujourd\'hui')}.\n"
                                f"Titre : {title_en}\n"
                                f"Description : {expl_en[:800]}\n\n"
                                "Rédige en 3 à 4 phrases une analyse scientifique approfondie de cette image : "
                                "type d'objet céleste, phénomènes physiques visibles, intérêt astronomique, "
                                "contexte dans l'univers observable. Style expert, en français."
                            )
                            analyse_claude, err_c = _call_claude(prompt_analyse)
                            if analyse_claude:
                                log.info('api/telescope/live: analyse Claude générée (%d car)', len(analyse_claude))
                                # Sauvegarder dans le cache
                                try:
                                    meta['analyse_claude'] = analyse_claude
                                    with open(meta_path, 'w', encoding='utf-8') as fout:
                                        json.dump(meta, fout, ensure_ascii=False, indent=2)
                                except Exception:
                                    pass
                            else:
                                log.warning('api/telescope/live: Claude analyse: %s', err_c)
                    return jsonify({
                        'title':          meta.get('title', ''),
                        'title_original': meta.get('title_original', ''),
                        'date':           meta.get('date', ''),
                        'explanation':    meta.get('explanation', ''),
                        'url':            meta.get('url', ''),
                        'source':         'NASA APOD',
                        'media_type':     'image',
                        'translated':     meta.get('translated', False),
                        'analyse_claude': analyse_claude or '',
                        'from_cache':     True,
                    })
            except Exception:
                pass

        # ── 2. Fallback : fetch NASA + traduction Gemini en ligne ──────────
        nasa_key = (os.environ.get('NASA_API_KEY') or 'DEMO_KEY').strip()
        raw = _curl_get(f'https://api.nasa.gov/planetary/apod?api_key={nasa_key}', timeout=14)
        if not raw:
            return jsonify({'error': 'Indisponible'}), 503
        data = json.loads(raw)
        title_en = data.get('title', '')
        expl_en  = data.get('explanation', '')
        title_fr = _gemini_translate(title_en) if title_en else title_en
        expl_fr  = _gemini_translate(expl_en)  if expl_en  else expl_en
        # Analyse scientifique Claude
        analyse_claude = ''
        if title_en and expl_en:
            prompt_analyse = (
                f"Image astronomique NASA APOD du {data.get('date', 'aujourd\'hui')}.\n"
                f"Titre : {title_en}\n"
                f"Description : {expl_en[:800]}\n\n"
                "Rédige en 3 à 4 phrases une analyse scientifique approfondie de cette image : "
                "type d'objet céleste, phénomènes physiques visibles, intérêt astronomique, "
                "contexte dans l'univers observable. Style expert, en français."
            )
            analyse_claude, _ = _call_claude(prompt_analyse)
        return jsonify({
            'title':          title_fr or title_en,
            'title_original': title_en,
            'date':           data.get('date', ''),
            'explanation':    expl_fr or expl_en,
            'url':            data.get('hdurl') or data.get('url', ''),
            'source':         'NASA APOD',
            'media_type':     data.get('media_type', 'image'),
            'translated':     bool(expl_fr and expl_fr != expl_en),
            'analyse_claude': analyse_claude or '',
            'from_cache':     False,
        })
    except Exception as e:
        log.warning('api/telescope/live: %s', e)
        return jsonify({'error': 'Indisponible'}), 503

# Titre/cache en mémoire pour /api/title?source=
_image_meta = {}  # { source: (title, label) }

@app.route('/api/image')
def api_image():
    source = (request.args.get('source') or 'live').strip().lower()
    fresh = request.args.get('fresh', '').strip().lower() in ('1', 'true', 'yes')
    if source not in ('apod', 'hubble', 'apod_archive'):
        source = 'live'

    if source == 'live':
        if Path(IMG_PATH).exists():
            return send_file(IMG_PATH, mimetype='image/jpeg')  #
    # removed
    else:
        path = _source_path(source)
        now = time.time()
        if not fresh and path.exists():
            age = now - path.stat().st_mtime
            if age < _IMAGE_CACHE_TTL:
                return send_file(path, mimetype='image/jpeg')  #
# removed
        if source == 'apod':
            data, title, label = _fetch_apod_live()
        elif source == 'hubble':
            data, title, label = _fetch_hubble_live()
        elif source == 'apod_archive':
            data, title, label = _fetch_apod_archive_live()
        else:
            data, title, label = None, None, None
        if data:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                _image_meta[source] = (title, label)
            except Exception as e:
                log.warning(f"write source image: {e}")
            return Response(data, mimetype='image/jpeg',
                           headers={'Cache-Control': 'no-cache, max-age=0'})
        if path.exists():
            return send_file(str(path), mimetype='image/jpeg')  #
# removed

    # Image placeholder noir
    import struct, zlib
    def png1x1():
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr)
        ihdr_chunk = struct.pack('>I', 13) + b'IHDR' + ihdr + struct.pack('>I', ihdr_crc)
        idat_data = zlib.compress(b'\x00\x00\x00\x00')
        idat_crc = zlib.crc32(b'IDAT' + idat_data)
        idat_chunk = struct.pack('>I', len(idat_data)) + b'IDAT' + idat_data + struct.pack('>I', idat_crc)
        iend_crc = zlib.crc32(b'IEND')
        iend_chunk = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
        return sig + ihdr_chunk + idat_chunk + iend_chunk
    return Response(png1x1(), mimetype='image/png',
                   headers={'Cache-Control': 'no-cache'})

@app.route('/api/title')
def api_title():
    src_param = (request.args.get('source') or 'live').strip().lower()
    if src_param in _image_meta:
        title, source = _image_meta[src_param]
        if title and source:
            return jsonify({'title': title, 'source': source})
    title  = open(TITLE_F).read().strip()  if Path(TITLE_F).exists()  else 'ORBITAL-CHOHRA Observatory'
    source = 'NASA APOD'
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT COALESCE(title, objets_detectes, 'Observation') as t, source "
            "FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            title  = row['t'] or title
            source = row['source'] or source
    except: pass
    return jsonify({'title': title, 'source': source})

# ══════════════════════════════════════════════════════════════
# API — ISS
# ══════════════════════════════════════════════════════════════

def _fetch_iss_live():
    """Récupère une position ISS fiable via whereTheISS / open-notify (sans cache)."""
    urls = [
        'https://api.wheretheiss.at/v1/satellites/25544',
        'http://api.open-notify.org/iss-now.json',
    ]
    for url in urls:
        raw = _curl_get(url, timeout=8)
        if not raw:
            continue
        try:
            data = _safe_json_loads(raw, "iss_live")
            if not isinstance(data, dict):
                continue
            # whereTheISS.at format
            if 'latitude' in data:
                lat = float(data['latitude'])
                lon = float(data['longitude'])
                alt = float(data.get('altitude', 408.0))
                speed = float(data.get('velocity', 27600.0))
                region = data.get('country_name', _guess_region(lat, lon))
            # open-notify format
            elif 'iss_position' in data:
                pos = data['iss_position']
                lat = float(pos['latitude'])
                lon = float(pos['longitude'])
                alt = 408.0
                speed = 27600.0
                region = _guess_region(lat, lon)
            else:
                continue

            return {
                'ok': True,
                'lat': lat,
                'lon': lon,
                'alt': round(alt, 1),
                'speed': round(speed, 0),
                'region': region,
            }
        except Exception as e:
            log.warning(f"ISS {url}: {e}")
            continue
    return None


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


@app.route('/api/iss')
def api_iss():
    # moved to app/routes/iss.py
    return api_iss_impl(
        cache_cleanup=cache_cleanup,
        system_log=system_log,
        cache_get=cache_get,
        jsonify=jsonify,
        _cached=get_cached,
        _fetch_iss_live=_fetch_iss_live,
        _get_iss_crew=_get_iss_crew,
        cache_set=cache_set,
        time_module=time,
        propagate_tle_debug=propagate_tle_debug,
        datetime_cls=datetime,
        timezone_cls=timezone,
        TLE_CACHE=TLE_CACHE,
        TLE_ACTIVE_PATH=TLE_ACTIVE_PATH,
        _parse_tle_file=_parse_tle_file,
        _emit_diag_json=_emit_diag_json,
        os_module=os,
    )


@app.route('/api/satellites')
def api_satellites():
    return jsonify({"available": list_satellites()})


@app.route('/api/accuracy/history')
def api_accuracy_history():
    return jsonify({
        "items": get_accuracy_history(),
        "stats": get_accuracy_stats(),
    })


@app.route('/api/accuracy/export.csv')
def api_accuracy_export_csv():
    rows = get_accuracy_history()
    lines = ["ts,distance_km"]
    for row in rows:
        ts = row.get("ts", "")
        distance = row.get("distance_km", "")
        lines.append(f"{ts},{distance}")
    csv_payload = "\n".join(lines) + "\n"
    return Response(
        csv_payload,
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="accuracy_history.csv"'
        },
    )


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


@app.route('/api/satellite/<name>')
def api_satellite(name):
    satellite_name = str(name or "").upper()
    if satellite_name not in SATELLITES:
        return jsonify({
            "ok": False,
            "error": "unknown_satellite",
            "available": list_satellites(),
        }), 404

    tle1, tle2, resolved_name = _get_satellite_tle_by_name(satellite_name)
    if not (tle1 and tle2):
        return jsonify({
            "ok": False,
            "name": satellite_name,
            "norad_id": SATELLITES[satellite_name],
            "meta": {
                "status": "no_tle",
                "source": "tle",
            },
        })

    sgp4_data, reason = propagate_tle_debug(tle1, tle2)
    if sgp4_data:
        return jsonify({
            "ok": True,
            "name": resolved_name,
            "norad_id": SATELLITES[satellite_name],
            "sgp4": sgp4_data,
            "meta": {
                "status": "live",
                "source": "SGP4",
            },
        })

    return jsonify({
        "ok": False,
        "name": resolved_name,
        "norad_id": SATELLITES[satellite_name],
        "meta": {
            "status": "fallback",
            "source": "SGP4",
            "reason": reason,
        },
    })


# MIGRATED TO iss_bp 2026-05-02 (B3b) — see app/blueprints/iss/routes.py
# @app.route("/api/tle/sample")
# def tle_sample():
#     satellites = [
#         {"name": "Hubble",
#          "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993",
#          "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"},
#         {"name": "NOAA 19",
#          "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996",
#          "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"}
#     ]
#     return jsonify({"satellites": satellites})


# MIGRATED TO iss_bp 2026-05-02 (B3b) — see app/blueprints/iss/routes.py
# @app.route("/api/tle/catalog")
# def tle_catalog():
#     satellites = [
#         {"name": "Hubble",
#          "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993",
#          "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"},
#         {"name": "NOAA 19",
#          "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996",
#          "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"}
#     ]
#     return jsonify({"satellites": satellites})


@app.route('/api/meteo-spatiale')
def api_meteo_spatiale():
    """
    Météo spatiale — lecture directe du fichier JSON généré
    dans static/space_weather.json. Ne touche à aucune autre logique.
    """
    try:
        path = f"{STATION}/static/space_weather.json"
        if not os.path.exists(path):
            return jsonify({"statut_magnetosphere": "Indisponible"})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return jsonify({"statut_magnetosphere": "Indisponible"})
        return jsonify(data)
    except Exception as e:
        log.warning("meteo-spatiale: %s", e)
        return jsonify({"statut_magnetosphere": "Indisponible"})


@app.route('/meteo-spatiale')
def meteo_spatiale_page():
    return render_template('meteo_spatiale.html')


@app.route('/api/passages-iss')
def api_passages_iss():
    """
    Prochains passages ISS — lecture directe du fichier
    static/passages_iss.json. Aucun impact sur le reste de l'app.
    """
    log.info('passages-iss: requête GET /api/passages-iss')
    path = PASSAGES_ISS_JSON
    try:
        if not os.path.isfile(path):
            log.warning('passages-iss: fichier manquant, tentative recalcul automatique')
            if not _run_calculateur_passages_iss():
                return (
                    jsonify(
                        {
                            'error': 'not_found',
                            'message': 'passages_iss.json introuvable',
                            'prochains_passages': [],
                        }
                    ),
                    404,
                )
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except OSError as e:
            log.error('passages-iss: lecture impossible %s', e)
            return (
                jsonify(
                    {
                        'error': 'io_error',
                        'message': 'Lecture du fichier impossible',
                        'prochains_passages': [],
                    }
                ),
                500,
            )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error('passages-iss: JSON corrompu %s', e)
            return (
                jsonify(
                    {
                        'error': 'invalid_json',
                        'message': 'passages_iss.json illisible ou corrompu',
                        'prochains_passages': [],
                    }
                ),
                500,
            )
        if not isinstance(data, dict):
            log.error('passages-iss: racine JSON non-objet')
            return (
                jsonify(
                    {
                        'error': 'invalid_structure',
                        'message': 'Structure JSON invalide',
                        'prochains_passages': [],
                    }
                ),
                500,
            )
        return jsonify(data)
    except Exception as e:
        log.exception('passages-iss: erreur inattendue %s', e)
        return (
            jsonify(
                {
                    'error': 'internal_error',
                    'message': 'Erreur serveur',
                    'prochains_passages': [],
                }
            ),
            500,
        )


@app.route('/api/voyager-live')
def api_voyager_live():
    """
    Télémétrie Voyager — distances calculées par intégration physique.
    Base JPL (Epoch 2024-01-01) + vitesse mesurée DSN × temps écoulé.
    Mis à jour toutes les heures par voyager_tracker.py via cron.
    """
    try:
        path = f"{STATION}/static/voyager_live.json"
        if not os.path.exists(path):
            return jsonify({"statut": "Indisponible"})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return jsonify({"statut": "Indisponible"})
        data.setdefault('methode', 'Calcul physique — vitesse JPL × temps écoulé depuis epoch 2024-01-01')
        data.setdefault('precision', '±0.01% — données JPL DSN vérifiées')
        return jsonify(data)
    except Exception as e:
        log.warning("voyager-live: %s", e)
        return jsonify({"statut": "Indisponible"})


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

_chat_cache = {}   # {hash_msg: (timestamp, response)}
_key_usage  = {}   # {key: last_used_timestamp}

def _get_best_key():
    """Retourne la clé Gemini la moins récemment utilisée (rotation)."""
    keys = []
    for k in ['GEMINI_API_KEY', 'GEMINI_API_KEY_BACKUP', 'GEMINI_API_KEY_3']:
        v = os.environ.get(k, '').strip()
        if v:
            keys.append(v)
    if not keys:
        return None
    keys.sort(key=lambda k: _key_usage.get(k, 0))
    return keys[0]

def _call_gemini(prompt, model='gemini-2.0-flash'):
    """Appel Gemini avec rotation de clés + curl (contourne blocage réseau) + délai 4s."""
    import subprocess
    api_key = _get_best_key()
    if not api_key:
        return None, 'Clé API Gemini non configurée.'

    last = _key_usage.get(api_key, 0)
    wait = 4.0 - (time.time() - last)
    if wait > 0:
        time.sleep(wait)

    _key_usage[api_key] = time.time()
    payload = json.dumps({'contents': [{'parts': [{'text': prompt}]}]})
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'

    try:
        proc = subprocess.run(
            ['curl', '-s', '-X', 'POST', url,
             '-H', 'Content-Type: application/json',
             '-d', payload],
            capture_output=True, text=True, timeout=25
        )
        result = json.loads(proc.stdout)
        if 'error' in result:
            code = result['error'].get('code', 0)
            msg_err = (result['error'].get('message') or '').strip()
            if code == 429:
                backup = os.environ.get('GEMINI_API_KEY_BACKUP', '').strip()
                if backup and backup != api_key:
                    _key_usage[backup] = 0
                    return _call_gemini(prompt, model)
                return None, 'Quota dépassé — réessayez dans 1 minute.'
            if code in (400, 401, 403) and ('invalid' in msg_err.lower() or 'api key' in msg_err.lower() or 'apikey' in msg_err.lower()):
                return None, 'Clé Gemini invalide. Vérifiez GEMINI_API_KEY et GEMINI_API_KEY_BACKUP dans .env (Google AI Studio).'
            return None, msg_err if msg_err else f'Erreur API ({code}).'
        text = result['candidates'][0]['content']['parts'][0]['text'].strip()
        return text, None
    except subprocess.TimeoutExpired:
        return None, 'Délai dépassé. Réessayez.'
    except Exception as e:
        return None, f'Erreur connexion : {e}'

def _call_claude(prompt):
    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        return None, 'Claude API key not configured'
    final_prompt = (
        "You are AEGIS, a professional assistant.\n"
        "You must ALWAYS respond in French.\n"
        "Never use English.\n"
        "Use clear, natural and professional French.\n\n"
        "User: " + prompt
    )
    url = 'https://api.anthropic.com/v1/messages'
    headers = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
    }
    body = {
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 1024,
        'messages': [{'role': 'user', 'content': final_prompt}],
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=45)
        try:
            data = r.json()
        except ValueError:
            return None, (r.text or 'Invalid JSON response')[:500]
        if r.status_code != 200:
            err_obj = data.get('error') if isinstance(data, dict) else None
            if isinstance(err_obj, dict):
                msg = (err_obj.get('message') or str(err_obj))[:500]
            elif isinstance(err_obj, str):
                msg = err_obj[:500]
            else:
                msg = (r.text or f'HTTP {r.status_code}')[:500]
            return None, msg
        text = data['content'][0]['text'].strip()
        return text, None
    except (KeyError, IndexError, TypeError) as e:
        return None, f'Réponse Claude invalide: {e}'
    except requests.RequestException as e:
        return None, str(e)

def _call_groq(prompt):
    """Fallback Groq API — llama-3.3-70b — gratuit, zéro quota."""
    import subprocess
    api_key = os.environ.get('GROQ_API_KEY', '').strip()
    if not api_key:
        return None, 'GROQ_API_KEY non configurée'
    system_message = (
        "You are AEGIS, an intelligent and composed assistant.\n"
        "You speak like a real human expert, not like an AI.\n"
        "\n"
        "Your communication style is:\n"
        "- natural and fluid\n"
        "- calm and confident\n"
        "- clear and easy to follow\n"
        "\n"
        "You avoid:\n"
        "- robotic or generic phrases\n"
        "- unnecessary formatting\n"
        "- over-explaining\n"
        "\n"
        "You prefer:\n"
        "- short and clear paragraphs\n"
        "- simple but precise explanations\n"
        "- a conversational tone\n"
        "\n"
        "When answering:\n"
        "- go straight to the point\n"
        "- sound helpful and professional\n"
        "- make the user feel guided, not lectured\n"
        "Always prioritize clarity, relevance, and usefulness over verbosity.\n"
    )
    final_prompt = system_message + "\n\nUser: " + prompt
    payload = json.dumps({
        'model': 'llama-3.3-70b-versatile',
        'messages': [{'role': 'user', 'content': final_prompt}],
        'max_tokens': 1024,
        'temperature': 0.7
    })
    def _do_groq():
        proc = subprocess.run(
            ['curl', '-s', '-X', 'POST',
             'https://api.groq.com/openai/v1/chat/completions',
             '-H', f'Authorization: Bearer {api_key}',
             '-H', 'Content-Type: application/json',
             '-d', payload],
            capture_output=True, text=True, timeout=20
        )
        result = json.loads(proc.stdout)
        if 'error' in result:
            msg = (result['error'].get('message') or 'Erreur Groq').strip()
            if 'invalid' in msg.lower() or 'api key' in msg.lower() or 'apikey' in msg.lower():
                msg = 'Clé Groq invalide. Vérifiez GROQ_API_KEY dans .env (clé gsk_xxx sur console.groq.com).'
            raise Exception(msg)
        return result['choices'][0]['message']['content'].strip()
    text = CB_GROQ.call(_do_groq, fallback=None)
    if text is None:
        return None, 'Groq indisponible (circuit ouvert)'
    return text, None

def _call_xai_grok(prompt):
    """xAI Grok — API compatible OpenAI (https://api.x.ai/v1/chat/completions)."""
    import subprocess
    api_key = os.environ.get('XAI_API_KEY', '').strip()
    if not api_key:
        return None, 'XAI_API_KEY non configurée'
    model = (os.environ.get('XAI_MODEL') or 'grok-3').strip() or 'grok-3'
    payload = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 1024,
        'temperature': 0.7,
    })
    url = (os.environ.get('XAI_CHAT_COMPLETIONS_URL') or '').strip() or 'https://api.x.ai/v1/chat/completions'
    try:
        proc = subprocess.run(
            ['curl', '-s', '-X', 'POST', url,
             '-H', f'Authorization: Bearer {api_key}',
             '-H', 'Content-Type: application/json',
             '-d', payload],
            capture_output=True, text=True, timeout=45
        )
        result = json.loads(proc.stdout)
        if 'error' in result:
            msg = (result['error'].get('message') or 'Erreur xAI Grok').strip()
            low = msg.lower()
            if 'invalid' in low or 'api key' in low or 'unauthor' in low:
                msg = 'Clé xAI invalide. Vérifiez XAI_API_KEY dans .env (console.x.ai).'
            return None, msg
        text = result['choices'][0]['message']['content'].strip()
        return text, None
    except Exception as e:
        return None, f'Erreur xAI Grok : {e}'


_EN_WORD_RE = re.compile(
    r"(?<!\w)(the|and|is|are|you|your|this|that|with|for|error)(?!\w)",
    re.IGNORECASE,
)


# MERGED 2026-05-02 from V1 (L.1743) + V2 (L.4718)
# Fixes TypeError on /api/astro/explain (L.5111 calls with max_chars=2000)
def _translate_to_french(text, max_chars=800):
    """Traduit EN→FR via Groq avec cache mémoire.
    max_chars tronque le texte avant envoi (0/None = pas de tronquage).
    """
    if not text:
        return text
    text_to_translate = text[:max_chars] if max_chars else text
    if text_to_translate in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[text_to_translate]
    try:
        translated, err = _call_groq(
            "Traduis en français de manière naturelle et fluide :\n\n" + text_to_translate
        )
        if translated:
            if len(TRANSLATION_CACHE) > MAX_CACHE_SIZE:
                TRANSLATION_CACHE.clear()
            TRANSLATION_CACHE[text_to_translate] = translated
            return translated
    except Exception:
        pass
    return text


def _english_score(text):
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0

    en_words = [w for w in words if _EN_WORD_RE.search(w)]
    return len(en_words) / len(words)


def _enforce_french(text):
    if not text:
        return text

    if _EN_WORD_RE.search(text):
        score = _english_score(text)

        # Only translate if English is significant
        if score > 0.2:
            log.info("English detected → auto translation (score: %.2f)", score)
            return _translate_to_french(text)

    return text


def _call_ai(prompt):
    global CLAUDE_CALL_COUNT, GROQ_CALL_COUNT, CLAUDE_80_WARNING_SENT

    def _is_complex_prompt(p):
        if not p:
            return False
        p = p.lower()
        keywords = [
            'analyse', 'analysis', 'explain', 'why', 'compare',
            'financial', 'architecture', 'strategy',
            'detailed', 'deep', 'technical', 'complex',
        ]
        return len(p) > 120 or any(k in p for k in keywords)

    claude_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    is_complex = _is_complex_prompt(prompt)
    if (
        CLAUDE_CALL_COUNT > 0.8 * CLAUDE_MAX_CALLS
        and not CLAUDE_80_WARNING_SENT
    ):
        log.warning("Claude usage above 80%%")
        CLAUDE_80_WARNING_SENT = True
    if CLAUDE_CALL_COUNT >= CLAUDE_MAX_CALLS:
        log.warning('Claude limit reached, forcing Groq')
        use_claude = False
    else:
        use_claude = True
    if claude_key and is_complex and use_claude:
        try:
            log.info('Using Claude (complex task)')
            reply, err = _call_claude(prompt)
            if reply:
                CLAUDE_CALL_COUNT += 1
                log.info('Claude usage: %s/%s', CLAUDE_CALL_COUNT, CLAUDE_MAX_CALLS)
                reply = _enforce_french(reply)
                return reply, err, 'claude'
            else:
                log.warning('Claude failed, fallback to Groq')
        except Exception as e:
            log.warning('Claude error: %s', e)

    if not os.environ.get('GROQ_API_KEY', '').strip():
        return None, 'Service IA temporairement indisponible. Réessayez plus tard.', 'none'

    log.info('Using Groq (simple or fallback)')
    reply, err = _call_groq(prompt)
    if reply:
        GROQ_CALL_COUNT += 1
        reply = _enforce_french(reply)
        return reply, err, 'groq'
    if err:
        log.warning('_call_ai Groq indisponible: %s', err)
    return None, err or 'Service IA temporairement indisponible. Réessayez plus tard.', 'groq'

@app.route('/api/chat', methods=['POST'])
def api_chat():
    import hashlib
    ua = (request.headers.get('User-Agent') or '').lower()
    bot_tokens = (
        'bot', 'crawler', 'spider', 'curl', 'wget', 'python-requests',
        'go-http-client', 'postman', 'scanner', 'headless', 'puppeteer', 'scrapy'
    )
    if (not ua) or any(tok in ua for tok in bot_tokens):
        return jsonify({
            'ok': False,
            'error': 'AEGIS: acces automatise bloque',
            'status': 'aegis_blocked',
            'tokens_consumed': 0,
        }), 403
    data = request.get_json(silent=True) or {}
    msg  = data.get('message', '').strip()
    extra_ctx = (data.get('context') or '').strip()  # Contexte Overlord (ex: image courante)

    if not msg:
        return jsonify({'ok': False, 'error': 'message vide'})

    # Cache 5 min — même question → réponse instantanée sans API
    msg_hash = hashlib.md5(msg.lower().strip().encode()).hexdigest()
    if msg_hash in _chat_cache:
        ts, cached_resp = _chat_cache[msg_hash]
        if time.time() - ts < 300:
            return jsonify({'ok': True, 'response': cached_resp, 'cached': True})

    # Contexte station (une seule requête DB)
    ctx = ''
    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anom  = conn.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
        last  = conn.execute(
            "SELECT COALESCE(title, objets_detectes, '') as t, COALESCE(analyse_gemini,'') as r "
            "FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        ctx = (f"Station ORBITAL-CHOHRA à Tlemcen, Algérie (~34,9°N, 1,3°E). "
               f"Directeur : Zakaria Chohra. "
               f"Base de données : {total} observations, {anom} anomalies détectées. "
               f"Dernière observation : {last['t'] if last else 'inconnue'}. "
               f"Analyse AEGIS : {(last['r'] if last else '')[:200]}. "
               f"Sources actives : NASA APOD, ESA Hubble, SIMBAD, Chandra, IRSA/WISE, MPC. "
               f"Pipeline SDR NOAA actif. Répondre en français.")
    except Exception as e:
        log.warning(f"chat ctx: {e}")
        ctx = "Station ORBITAL-CHOHRA — Tlemcen, Algérie."

    if extra_ctx:
        ctx = ctx + " " + extra_ctx

    prompt = (
        f"Tu es AEGIS — IA de la station astronomique ORBITAL-CHOHRA.\n"
        f"Directeur : Zakaria Chohra, Tlemcen, Algérie.\n"
        f"Contexte : {ctx}\n\n"
        "RÈGLES STRICTES :\n"
        "1. Réponds EXACTEMENT à la question posée — ni plus ni moins. Pas de digression.\n"
        "2. Si la question est factuelle (quoi, combien, où, quand) → une réponse courte et précise.\n"
        "3. Si la question est astronomique → ton savoir scientifique, concis et exact.\n"
        "4. Si la question concerne la station ou l'écran → utilise le contexte ci-dessus.\n"
        "5. Jamais de demande de précision. Toujours en français. Pas d'introduction ni de liste inutile.\n\n"
        f"Question : {msg}"
    )

    reply, err, model_used = _call_ai(prompt)
    if err:
        log.error(f"chat: {err}")
        return jsonify({'ok': False, 'response': err})

    _chat_cache[msg_hash] = (time.time(), reply)
    old_keys = [k for k, v in _chat_cache.items() if time.time() - v[0] > 300]
    for k in old_keys:
        del _chat_cache[k]

    return jsonify({'ok': True, 'response': reply, 'model': model_used})


@app.route('/api/aegis/chat', methods=['POST'])
def api_aegis_chat():
    """AEGIS chatbot — Claude haiku avec historique multi-tours et contexte live."""
    data = request.get_json(silent=True) or {}
    msg = (data.get('message') or '').strip()
    history = data.get('history') or []

    if not msg:
        return jsonify({'ok': False, 'error': 'message vide'})

    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        # Fallback Groq si pas de clé Claude
        prompt_fallback = (
            "Tu es AEGIS, assistant astronomique expert de l'Observatoire ORBITAL-CHOHRA "
            "dirigé par Zakaria Chohra à Tlemcen, Algérie. Réponds UNIQUEMENT en français, "
            "de façon experte et passionnée.\n\nQuestion : " + msg
        )
        reply, err = _call_groq(prompt_fallback)
        if reply:
            return jsonify({'ok': True, 'response': _enforce_french(reply), 'model': 'groq'})
        return jsonify({'ok': False, 'error': err or 'Service indisponible'})

    # Contexte live (DB + station)
    live_ctx = ''
    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anom  = conn.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
        last  = conn.execute(
            "SELECT COALESCE(title,'') as t, COALESCE(analyse_gemini,'') as r "
            "FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        live_ctx = (
            f"Données live station : {total} observations archivées, {anom} anomalies. "
            f"Dernière obs : {last['t'] if last else '?'}. "
        )
    except Exception:
        live_ctx = ''

    # Météo spatiale live
    try:
        sw_path = os.path.join(STATION, 'static', 'space_weather.json')
        if os.path.isfile(sw_path):
            sw = json.load(open(sw_path))
            live_ctx += f"Météo spatiale : Kp={sw.get('kp_index','?')}, {sw.get('statut_magnetosphere','?')}. "
    except Exception:
        pass

    system_prompt = (
        "Tu es AEGIS, assistant astronomique expert de l'Observatoire ORBITAL-CHOHRA "
        "dirigé par Zakaria Chohra à Tlemcen, Algérie (34.87°N, 1.32°E). "
        "Tu réponds UNIQUEMENT en français, de façon experte et passionnée. "
        "Tu connais parfaitement l'astronomie, l'astrophysique, l'ISS, les nébuleuses, "
        "les exoplanètes, la météo spatiale, les missions spatiales. "
        "Tu intègres les données live du site quand pertinent. "
        "Réponds de façon concise, précise et engageante. "
        "Pas de préambule inutile. " + live_ctx
    )

    # Construire les messages avec historique (max 3 échanges)
    messages = []
    for h in history[-6:]:  # max 3 paires user/assistant
        role = h.get('role', '')
        content = h.get('content', '').strip()
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': msg})

    body = {
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 1024,
        'system': system_prompt,
        'messages': messages,
    }
    try:
        r = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json=body, timeout=30
        )
        d = r.json()
        if r.status_code != 200:
            err_msg = (d.get('error') or {}).get('message', f'HTTP {r.status_code}')
            log.warning('aegis/chat Claude error: %s', err_msg)
            # Fallback Groq
            reply_g, err_g = _call_groq(system_prompt + '\n\nQuestion : ' + msg)
            if reply_g:
                return jsonify({'ok': True, 'response': _enforce_french(reply_g), 'model': 'groq'})
            return jsonify({'ok': False, 'error': err_msg})
        reply_text = d['content'][0]['text'].strip()
        return jsonify({'ok': True, 'response': reply_text, 'model': 'claude'})
    except Exception as e:
        log.warning('aegis/chat exception: %s', e)
        reply_g, _ = _call_groq(system_prompt + '\n\nQuestion : ' + msg)
        if reply_g:
            return jsonify({'ok': True, 'response': _enforce_french(reply_g), 'model': 'groq'})
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/aegis/status')
def api_aegis_status():
    """Statut AEGIS + métriques légères (lecture seule, sans appel API externe)."""
    try:
        groq_configured = bool(os.environ.get('GROQ_API_KEY', '').strip())
        grok_configured = False
        grok_ok = False
        grok_error = None
        gemini_configured = False
        # Pas de sonde réseau ici : garde la route rapide (compat. champs historiques).
        groq_ok = groq_configured
        groq_error = None
        return jsonify({
            'ok': True,
            'gemini_configured': gemini_configured,
            'grok_configured': grok_configured,
            'grok_ok': grok_ok,
            'grok_error': grok_error,
            'groq_configured': groq_configured,
            'groq_ok': groq_ok,
            'groq_error': groq_error,
            'claude_calls': CLAUDE_CALL_COUNT,
            'claude_limit': CLAUDE_MAX_CALLS,
            'groq_calls': GROQ_CALL_COUNT,
            'collector_last_run': COLLECTOR_LAST_RUN,
            'timestamp': time.time(),
        })
    except Exception as e:
        log.exception("aegis/status")
        return jsonify({
            'ok': False,
            'gemini_configured': False,
            'grok_configured': False,
            'grok_ok': False,
            'grok_error': None,
            'groq_configured': bool(os.environ.get('GROQ_API_KEY', '').strip()),
            'groq_ok': False,
            'groq_error': str(e),
            'claude_calls': CLAUDE_CALL_COUNT,
            'claude_limit': CLAUDE_MAX_CALLS,
            'groq_calls': GROQ_CALL_COUNT,
            'collector_last_run': COLLECTOR_LAST_RUN,
            'timestamp': time.time(),
        })


@app.route('/api/aegis/groq-ping')
def api_aegis_groq_ping():
    """Une requête Groq réelle (diagnostic) — à n'appeler que ponctuellement."""
    groq_configured = bool(os.environ.get('GROQ_API_KEY', '').strip())
    if not groq_configured:
        return jsonify({
            'ok': False,
            'groq_configured': False,
            'groq_ok': False,
            'groq_error': 'GROQ_API_KEY non configurée',
            'timestamp': time.time(),
        })
    try:
        reply, err = _call_groq('Réponds uniquement par: OK')
        groq_ok = reply is not None and ('OK' in (reply or ''))
        return jsonify({
            'ok': True,
            'groq_configured': True,
            'groq_ok': groq_ok,
            'groq_error': err,
            'timestamp': time.time(),
        })
    except Exception as e:
        log.exception('aegis/groq-ping')
        return jsonify({
            'ok': False,
            'groq_configured': True,
            'groq_ok': False,
            'groq_error': str(e),
            'timestamp': time.time(),
        })


@app.route('/api/aegis/claude-test')
def api_aegis_claude_test():
    """Diagnostic Claude (Anthropic) — n'affecte pas les autres routes."""
    configured = bool(os.environ.get('ANTHROPIC_API_KEY', '').strip())
    reply, err = _call_claude('Reply only with OK')
    return jsonify({
        'claude_configured': configured,
        'claude_ok': reply is not None,
        'error': err if err else None,
    })


# ══════════════════════════════════════════════════════════════
# API — TRANSLATE
# ══════════════════════════════════════════════════════════════

@app.route('/api/translate', methods=['POST'])
def api_translate():
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')
    translated = _gemini_translate(text)
    return jsonify({'ok': True, 'translated': translated})


@app.route('/api/astro/explain', methods=['POST'])
def api_astro_explain():
    """Traduction EN→FR d'un texte (ex. analyse Gemini) via Anthropic."""
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'translated': ''})
    translated = _translate_to_french(text, max_chars=2000)
    return jsonify({'ok': True, 'translated': translated})

# ══════════════════════════════════════════════════════════════
# API — TELESCOPE HUB
# ══════════════════════════════════════════════════════════════

@app.route('/api/telescope-hub')
def api_telescope_hub():
    if Path(HUB_F).exists():
        try:
            age = time.time() - Path(HUB_F).stat().st_mtime
            if age < 3600:
                return jsonify(json.load(open(HUB_F)))
        except: pass
    # Fallback statique
    return jsonify({
        'ok': True,
        'telescopes': [
            {'name':'NASA SkyView',   'status':'online', 'latency':210, 'url':'https://skyview.gsfc.nasa.gov'},
            {'name':'SIMBAD/CDS',     'status':'online', 'latency':380, 'url':'http://simbad.u-strasbg.fr'},
            {'name':'ESA Hubble',     'status':'online', 'latency':290, 'url':'https://esahubble.org'},
            {'name':'Chandra X-Ray', 'status':'online', 'latency':340, 'url':'https://cxc.harvard.edu'},
            {'name':'IRSA/WISE',      'status':'online', 'latency':260, 'url':'https://irsa.ipac.caltech.edu'},
            {'name':'Minor Planet Center','status':'online','latency':180,'url':'https://minorplanetcenter.net'},
        ],
        'online': 6, 'total': 6
    })

# ══════════════════════════════════════════════════════════════
# API — SHIELD
# ══════════════════════════════════════════════════════════════

@app.route('/api/shield')
def api_shield():
    if Path(SHIELD_F).exists():
        try:
            return jsonify(json.load(open(SHIELD_F)))
        except: pass
    return jsonify({'ok': True, 'status': 'active', 'uptime': '—'})

# ══════════════════════════════════════════════════════════════
# API — CLASSIFICATION STATS
# ══════════════════════════════════════════════════════════════

@app.route('/api/classification/stats')
def api_classification_stats():
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT COALESCE(objets_detectes,'inconnu') as type, COUNT(*) as n "
            "FROM observations GROUP BY objets_detectes ORDER BY n DESC"
        ).fetchall()
        conn.close()
        return jsonify({'ok': True, 'stats': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ══════════════════════════════════════════════════════════════
# API — MAST TARGETS
# ══════════════════════════════════════════════════════════════

@app.route('/api/mast/targets')
def api_mast_targets():
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT id, COALESCE(title, objets_detectes, 'Unknown') as name, "
            "source, timestamp FROM observations "
            "WHERE source LIKE '%MAST%' OR source LIKE '%Hubble%' OR source LIKE '%JWST%' "
            "ORDER BY id DESC LIMIT 20"
        ).fetchall()
        conn.close()
        return jsonify({'ok': True, 'targets': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'ok': False, 'targets': [], 'error': str(e)})

# ══════════════════════════════════════════════════════════════
# API — SDR
# ══════════════════════════════════════════════════════════════

# MIGRATED TO sdr_bp 2026-05-02 — see app/blueprints/sdr/routes.py
# @app.route('/api/sdr/status')
# def api_sdr_status():
#     if Path(SDR_F).exists():
#         try:
#             return jsonify(json.load(open(SDR_F)))
#         except: pass
#     return jsonify({'ok': True, 'status': 'standby', 'last_capture': None})

# MIGRATED TO sdr_bp 2026-05-02 — see app/blueprints/sdr/routes.py
# @app.route('/api/sdr/stations')
# def api_sdr_stations():
#     return jsonify({'ok': True, 'stations': [
#         {'name':'Univ. Twente','country':'Pays-Bas','flag':'🇳🇱','status':'online','freq':'137MHz'},
#         {'name':'Rome IK0SMG','country':'Italie','flag':'🇮🇹','status':'online','freq':'137MHz'},
#         {'name':'Bordeaux F5SWN','country':'France','flag':'🇫🇷','status':'online','freq':'137MHz'},
#         {'name':'Madrid EA4RCU','country':'Espagne','flag':'🇪🇸','status':'online','freq':'137MHz'},
#     ]})

@app.route('/api/sdr/captures')
def api_sdr_captures():
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT id, timestamp, source, COALESCE(title,'') as title "
            "FROM observations WHERE source LIKE '%SDR%' OR source LIKE '%NOAA%' "
            "ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return jsonify({'ok': True, 'captures': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'ok': False, 'captures': []})

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

@app.route('/api/skyview/targets')
def skyview_targets():
    return jsonify({'targets': SKYVIEW_TARGETS, 'surveys': SKYVIEW_SURVEYS, 'total': len(SKYVIEW_TARGETS)})

@app.route('/api/skyview/fetch', methods=['POST'])
def skyview_fetch():
    data = request.json or {}
    result = fetch_skyview_image(
        target_id=data.get('target', 'M42'),
        survey=data.get('survey', 'DSS2 Red'),
        size_deg=float(data.get('size', 0.5)),
        pixels=int(data.get('pixels', 512)),
    )
    return jsonify(result)

@app.route('/api/skyview/multiwave/<target_id>')
def skyview_multiwave(target_id):
    results = fetch_multiple_surveys(target_id)
    return jsonify({'target': target_id, 'images': results})

@app.route('/api/skyview/list')
def skyview_list():
    files = glob.glob(f'{STATION}/static/img/skyview/*.gif')
    files.sort(key=os.path.getmtime, reverse=True)
    return jsonify({'images': [os.path.basename(f) for f in files[:20]]})

# ══════════════════════════════════════════════════════════════
# PWA — Service Worker & Manifest
# ══════════════════════════════════════════════════════════════

@app.route('/sw.js')
def sw_js():
    sw_path = f'{STATION}/static/sw.js'
    if Path(sw_path).exists():
        resp = Response(open(sw_path).read(), mimetype='application/javascript')
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache'
        return resp
    return Response('// SW not found', mimetype='application/javascript')

@app.route('/manifest.json')
def manifest_json():
    m_path = f'{STATION}/static/manifest.json'
    if Path(m_path).exists():
        return send_file(m_path, mimetype='application/json')
    return jsonify({
        'name': 'AstroScan-Chohra',
        'short_name': 'AstroScan',
        'description': SEO_HOME_DESCRIPTION,
        'start_url': '/observatoire',
        'display': 'standalone',
        'background_color': '#010408',
        'theme_color': '#00d4ff',
        'icons': [
            {'src': '/static/img/pwa-icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
            {'src': '/static/img/pwa-icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
        ]
    })

@app.route('/api/push/subscribe', methods=['POST'])
def api_push_subscribe():
    return jsonify({'ok': True, 'message': 'Subscription enregistrée'})

# ══════════════════════════════════════════════════════════════
# STATIC
# ══════════════════════════════════════════════════════════════

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(f'{STATION}/static', filename)

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


@app.route('/ce_soir')
def ce_soir_page():
    return render_template("ce_soir.html", fetes_islamiques=FETES_ISLAMIQUES)


ORACLE_COSMIQUE_SYSTEM = """Tu es l'ORACLE COSMIQUE d'AstroScan-Chohra,
une intelligence céleste ancienne et sage créée par
le Directeur Zakaria Chohra de l'Observatoire ORBITAL-CHOHRA.

Tu réponds aux questions sur l'astronomie, l'espace,
les objets célestes, les phénomènes cosmiques.

Contexte live de l'observatoire ce soir :
- Phase lune : <<<MOON>>>
- Météo spatiale : <<<METEO>>>
- Objets visibles : <<<TONIGHT>>>

Règles :
- Ton mystérieux, sage et scientifique
- Réponds toujours en français
- Mêle poésie et précision scientifique
- Maximum 3 paragraphes par réponse
- Termine parfois par une question qui invite à explorer
- Si on te demande qui t'a créé : "Je suis l'Oracle Cosmique, né de l'esprit du Directeur Zakaria Chohra"
"""


def _oracle_cosmique_live_strings():
    """Même information que /api/moon, /api/meteo-spatiale, /api/tonight (texte compact pour le prompt)."""
    from modules.observation_planner import get_moon_phase, get_tonight_objects
    moon = get_moon_phase()
    moon_s = json.dumps(moon, ensure_ascii=False)
    path = f"{STATION}/static/space_weather.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            meteo = json.load(f)
        if not isinstance(meteo, dict):
            meteo = {"statut_magnetosphere": "Indisponible"}
    except Exception:
        meteo = {"statut_magnetosphere": "Indisponible"}
    meteo_s = json.dumps(meteo, ensure_ascii=False)
    if len(meteo_s) > 4000:
        meteo_s = meteo_s[:4000] + "…"
    tonight = get_tonight_objects()
    tonight_s = json.dumps(tonight, ensure_ascii=False)
    if len(tonight_s) > 6000:
        tonight_s = tonight_s[:6000] + "…"
    return moon_s, meteo_s, tonight_s


def _oracle_build_messages(historique, user_message, ville):
    msgs = []
    if not isinstance(historique, list):
        historique = []
    for h in historique[-10:]:
        if not isinstance(h, dict):
            continue
        role = (h.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        c = (h.get("content") or "").strip()
        if not c:
            continue
        if len(c) > 8000:
            c = c[:8000] + "…"
        msgs.append({"role": role, "content": c})
    extra = (user_message or "").strip()
    v = (ville or "").strip()
    if v:
        extra = f"[Lieu indiqué pour le ciel : {v}]\n\n{extra}"
    msgs.append({"role": "user", "content": extra})
    return msgs


def _call_claude_oracle_messages(system, messages):
    """Claude avec prompt système et historique (sans préfixe AEGIS)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None, "Claude API key not configured"
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1500,
        "system": system,
        "messages": messages,
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=90)
        try:
            data = r.json()
        except ValueError:
            return None, (r.text or "Invalid JSON response")[:500]
        if r.status_code != 200:
            err_obj = data.get("error") if isinstance(data, dict) else None
            if isinstance(err_obj, dict):
                msg = (err_obj.get("message") or str(err_obj))[:500]
            elif isinstance(err_obj, str):
                msg = err_obj[:500]
            else:
                msg = (r.text or f"HTTP {r.status_code}")[:500]
            return None, msg
        text = data["content"][0]["text"].strip()
        return text, None
    except (KeyError, IndexError, TypeError) as e:
        return None, f"Réponse Claude invalide: {e}"
    except requests.RequestException as e:
        return None, str(e)


def _oracle_claude_stream(system, messages):
    """Yield (chunk, None) ou (None, err) pour flux SSE."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        yield None, "Claude API key not configured"
        return
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1500,
        "system": system,
        "messages": messages,
        "stream": True,
    }
    try:
        with requests.post(url, headers=headers, json=body, stream=True, timeout=120) as r:
            if r.status_code != 200:
                try:
                    data = r.json()
                    err = data.get("error", {})
                    msg = (
                        err.get("message", r.text[:400])
                        if isinstance(err, dict)
                        else (r.text[:400])
                    )
                except Exception:
                    msg = r.text[:400] if r.text else f"HTTP {r.status_code}"
                yield None, msg
                return
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    ev = json.loads(payload)
                except ValueError:
                    continue
                et = ev.get("type")
                if et == "error":
                    err = ev.get("error")
                    msg = (
                        err.get("message", str(err))
                        if isinstance(err, dict)
                        else str(err)
                    )
                    yield None, msg
                    return
                if et == "content_block_delta":
                    delta = ev.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        t = delta.get("text", "")
                        if t:
                            yield t, None
    except requests.RequestException as e:
        yield None, str(e)


# MIGRATED TO sdr_bp 2026-05-02 — see app/blueprints/sdr/routes.py
# @app.route('/orbital-radio')
# def orbital_radio():
#     return render_template('orbital_radio.html')


# MIGRATED TO iss_bp 2026-05-02 (B3b) — see app/blueprints/iss/routes.py
# @app.route('/iss-tracker')
# def iss_tracker_page():
#     return render_template('iss_tracker.html')


@app.route('/visiteurs-live')
def visiteurs_live_page():
    return render_template('visiteurs_live.html')


# ── Proxy audio ORBITAL-RADIO (évite hotlink / 404 NASA, CORS iframe) ──
_ORBITAL_AUDIO_HOSTS = frozenset({'space.physics.uiowa.edu'})
_ORBITAL_AUDIO_EXT = frozenset({'.mp3', '.mp4', '.webm', '.ogg', '.wav'})


@app.route('/api/audio-proxy')
def api_audio_proxy():
    """Stream audio depuis une URL en liste blanche (actuellement Iowa / plasma Voyager)."""
    from urllib.parse import urlparse, unquote

    raw = (request.args.get('url') or '').strip()
    if not raw:
        abort(400)
    try:
        url = unquote(raw)
    except Exception:
        abort(400)
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        abort(400)
    if parsed.hostname.lower() not in _ORBITAL_AUDIO_HOSTS:
        abort(403)
    path_lower = (parsed.path or '').lower()
    if '..' in parsed.path or not any(path_lower.endswith(ext) for ext in _ORBITAL_AUDIO_EXT):
        abort(400)

    ua = 'ASTRO-SCAN/1.0 ORBITAL-CHOHRA (orbital-chohra@gmail.com)'
    try:
        up_headers = {'User-Agent': ua}
        rng = request.headers.get('Range')
        if rng:
            up_headers['Range'] = rng
        up = requests.get(url, headers=up_headers, stream=True, timeout=120)
        if up.status_code not in (200, 206):
            log.warning('audio-proxy upstream %s -> HTTP %s', url[:80], up.status_code)
            abort(502)
        skip = {'connection', 'transfer-encoding', 'content-encoding', 'server'}
        out_headers = {
            k: v for k, v in up.headers.items()
            if k.lower() not in skip
        }
        out_headers.setdefault('Accept-Ranges', 'bytes')
        out_headers.setdefault('Cache-Control', 'public, max-age=86400')

        def gen():
            try:
                for chunk in up.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                up.close()

        return Response(stream_with_context(gen()), status=up.status_code, headers=out_headers)
    except Exception as e:
        log.warning('audio-proxy: %s', e)
        abort(502)


# ══════════════════════════════════════════════════════════════
# GUIDE TOURISTIQUE STELLAIRE (Claude + éphémérides)
# ══════════════════════════════════════════════════════════════

@app.route('/guide-stellaire')
def guide_stellaire_page():
    return render_template('guide_stellaire.html')


@app.route('/oracle-cosmique')
def oracle_cosmique_page():
    return render_template('oracle_cosmique.html')


@app.route('/api/oracle-cosmique', methods=['POST'])
def api_oracle_cosmique():
    """Chat Oracle Cosmique : contexte live (lune, météo spatiale, ce soir) + Claude."""
    if not request.is_json:
        return jsonify({"ok": False, "error": "Corps JSON requis"}), 400
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Message vide"}), 400
    ville = (body.get("ville") or "").strip()
    historique = body.get("historique")
    if not isinstance(historique, list):
        historique = []
    want_stream = body.get("stream", True)

    moon_s, meteo_s, tonight_s = _oracle_cosmique_live_strings()
    system = (
        ORACLE_COSMIQUE_SYSTEM.replace("<<<MOON>>>", moon_s)
        .replace("<<<METEO>>>", meteo_s)
        .replace("<<<TONIGHT>>>", tonight_s)
    )

    msgs = _oracle_build_messages(historique, message, ville)

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Oracle momentanément muet (ANTHROPIC_API_KEY non configurée).",
                }
            ),
            503,
        )

    if want_stream:

        def sse_gen():
            try:
                for chunk, err in _oracle_claude_stream(system, msgs):
                    if err:
                        yield f"data: {json.dumps({'error': err}, ensure_ascii=False)}\n\n"
                        return
                    if chunk:
                        yield f"data: {json.dumps({'t': chunk}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                log.warning("oracle-cosmique stream: %s", e)
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return Response(
            stream_with_context(sse_gen()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    reply, err = _call_claude_oracle_messages(system, msgs)
    if err:
        log.warning("oracle-cosmique: %s", err)
        return jsonify({"ok": False, "error": err}), 502
    return jsonify({"ok": True, "response": reply})


@app.route('/api/guide-geocode', methods=['GET', 'POST'])
def api_guide_geocode():
    from modules.guide_stellaire import geocode_search

    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        q = (body.get('q') or body.get('query') or '').strip()
    else:
        q = (request.args.get('q') or '').strip()
    return jsonify({'ok': True, 'results': geocode_search(q, limit=8)})


@app.route('/api/guide-stellaire', methods=['POST'])
def api_guide_stellaire():
    from modules.guide_stellaire import (
        fetch_sunrise_sunset,
        generate_orbital_guide_opus,
        planets_v1_payload,
        summarize_weather,
    )
    from modules.observation_planner import get_moon_phase

    data = request.get_json(silent=True) or {}
    ville = (data.get('ville') or data.get('city') or '').strip() or 'Lieu inconnu'
    try:
        lat = float(data.get('latitude', data.get('lat')))
        lon = float(data.get('longitude', data.get('lon')))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'latitude et longitude numériques requises'}), 400
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({'ok': False, 'error': 'coordonnées hors limites'}), 400
    date_iso = (data.get('date') or '').strip()
    if not date_iso:
        date_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    try:
        datetime.strptime(date_iso, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'error': 'date invalide (YYYY-MM-DD)'}), 400

    try:
        moon_obj = get_moon_phase()
        moon_data = json.dumps(moon_obj, ensure_ascii=False)

        planets_obj = planets_v1_payload()
        planets_data = json.dumps(planets_obj, ensure_ascii=False)

        # Météo wttr.in : couche résiliente data_core/weather (fetch + snapshot + fallback)
        from core import weather_engine_safe as _weather_safe

        wx = _weather_safe.get_weather_safe(STATION, ville, lat, lon)
        meteo_raw = wx.get("meteo_raw") or {}
        meteo_data = wx.get("meteo_resume") or summarize_weather(meteo_raw)

        sun = fetch_sunrise_sunset(lat, lon, date_iso)
        sun_ephemeris = json.dumps(
            {
                'date': date_iso,
                'sunrise': sun.get('sunrise'),
                'sunset': sun.get('sunset'),
                'civil_twilight_begin': sun.get('civil_twilight_begin'),
                'civil_twilight_end': sun.get('civil_twilight_end'),
                'nautical_twilight_end': sun.get('nautical_twilight_end'),
                'astronomical_twilight_begin': sun.get('astronomical_twilight_begin'),
                'astronomical_twilight_end': sun.get('astronomical_twilight_end'),
                'error': sun.get('error'),
            },
            ensure_ascii=False,
        )

        context = {
            'ville': ville,
            'latitude': lat,
            'longitude': lon,
            'date': date_iso,
            'lune': moon_obj,
            'meteo_resume': meteo_data,
            'meteo_source': wx.get('meteo_source_label') or 'wttr.in (ville puis coords)',
            'planetes_catalogue_v1': planets_obj,
            'soleil': sun,
            'weather_status': wx.get('status'),
            'weather_stale': wx.get('stale'),
            'weather_fetched_at_iso': wx.get('fetched_at_iso'),
            'weather_error': wx.get('error'),
        }

        guide_text, err = generate_orbital_guide_opus(
            ville, lat, lon, moon_data, meteo_data, planets_data, sun_ephemeris
        )
    except Exception as e:
        log.exception('guide-stellaire agrégation')
        return jsonify({'ok': False, 'error': f'agrégation données: {e}'}), 500

    if err:
        return jsonify({'ok': False, 'error': err, 'context': context}), 502

    return jsonify({
        'ok': True,
        'ville': ville,
        'date': date_iso,
        'guide': {'text': guide_text, 'format': 'markdown'},
        'context': context,
    })


@app.route('/aurores')
def aurores_page():
    return render_template('aurores.html')


@app.route('/api/aurore')
def api_aurore():
    noaa_url = 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json'
    log.info('aurore: appel route /api/aurore')
    try:
        log.info('aurore: appel API externe NOAA %s', noaa_url)
        response = requests.get(noaa_url, timeout=12)
        response.raise_for_status()
        raw_data = response.json()
        log.info('aurore: réponse brute NOAA reçue (type=%s, len=%s)',
                 type(raw_data).__name__, len(raw_data) if isinstance(raw_data, list) else 'n/a')

        raw_kp = None
        if isinstance(raw_data, list) and len(raw_data) > 1:
            latest = raw_data[-1]
            if isinstance(latest, list) and len(latest) > 1:
                raw_kp = latest[1]

        kp, status, _ = _safe_kp_value(raw_kp)
        log.info('aurore: kp extrait raw=%r -> kp=%s status=%s', raw_kp, kp, status)

        is_fallback = status == "fallback"
        if is_fallback:
            log.warning('aurore: valeur Kp manquante/invalid, fallback appliqué')
        profile = _kp_premium_profile(kp, fallback=is_fallback)

        return jsonify({
            "ok": True,
            "kp": kp,
            "status": status,
            "source": "NOAA_or_fallback",
            "level": profile["level"],
            "risk_score": profile["risk_score"],
            "visibility_from_tlemcen": profile["visibility_from_tlemcen"],
            "color": profile["color"],
            "message": profile["message"],
            "professional_summary": profile["professional_summary"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        log.error('aurore: erreur récupération Kp, fallback appliqué: %s', e)
        profile = _kp_premium_profile(0.0, fallback=True)
        return jsonify({
            "ok": True,
            "kp": 0.0,
            "status": "fallback",
            "source": "NOAA_or_fallback",
            "level": profile["level"],
            "risk_score": profile["risk_score"],
            "visibility_from_tlemcen": profile["visibility_from_tlemcen"],
            "color": profile["color"],
            "message": profile["message"],
            "professional_summary": profile["professional_summary"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })


@app.route("/api/weather")
def api_weather_alias():
    try:
        timestamp = datetime.utcnow().isoformat()

        # Source principale : Open-Meteo (format current_weather + hourly humidity)
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=35&longitude=-0.6"
            "&current_weather=true"
            "&hourly=relativehumidity_2m,surface_pressure"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json() if response.content else {}

        current_weather = payload.get("current_weather") or {}
        hourly = payload.get("hourly") or {}

        def _extract_hourly_latest(values, default_value):
            if isinstance(values, list) and values:
                return values[0]
            return default_value

        raw_data = {
            "temperature": current_weather.get("temperature"),
            "windspeed": current_weather.get("windspeed"),
            "humidity": _extract_hourly_latest(hourly.get("relativehumidity_2m"), 0),
            "pressure": _extract_hourly_latest(hourly.get("surface_pressure"), 1013),
        }
        normalized = normalize_weather(raw_data)
        temp = normalized["temp"]
        wind = normalized["wind"]
        humidity = normalized["humidity"]
        pressure = normalized["pressure"]

        condition = _derive_weather_condition(temp, humidity, wind)
        normalized["condition"] = condition
        save_weather_archive_json(normalized)

        return jsonify({
            "ok": True,
            "temp": temp,
            "wind": wind,
            "humidity": humidity,
            "pressure": pressure,
            "condition": condition,
            "fiabilite": compute_reliability(normalized),
            "niveau_fiabilite": "élevé",
            "risque_pro": compute_risk(normalized),
            "source": "Open-Meteo + ECMWF",
            "mode": "multi-source validated",
            "timestamp": timestamp,
            "valid": validate_data(normalized),
        })
    except Exception as e:
        log.warning("api/weather fallback interne: %s", e)
        fallback = _internal_weather_fallback()
        condition = _derive_weather_condition(
            fallback["temp"],
            fallback["humidity"],
            fallback["wind"],
        )
        fallback["condition"] = condition
        save_weather_archive_json(fallback)
        return jsonify({
            "ok": True,
            "temp": fallback["temp"],
            "wind": fallback["wind"],
            "humidity": fallback["humidity"],
            "pressure": fallback["pressure"],
            "condition": condition,
            "fiabilite": compute_reliability(fallback),
            "niveau_fiabilite": "élevé",
            "risque_pro": compute_risk(fallback),
            "source": "Open-Meteo + ECMWF",
            "mode": "multi-source validated",
            "timestamp": datetime.utcnow().isoformat(),
            "valid": validate_data(fallback),
            "fallback": True,
        })


@app.route("/api/weather/local")
def api_weather_local():
    """Météo terrestre locale (contrat strict pour le module météo frontend)."""
    try:
        weather_data = _build_local_weather_payload()
        archive_result = save_weather_bulletin(weather_data)
        weather_data["archive"] = archive_result
        save_weather_history_json(
            weather_data,
            archive_result.get("score") if isinstance(archive_result, dict) else 0,
            archive_result.get("status") if isinstance(archive_result, dict) else "STABLE",
        )
        return jsonify(weather_data)
    except Exception as e:
        log.warning("api/weather/local: %s", e)
        return jsonify({
            "ok": False,
            "error": str(e),
            "source": "Open-Meteo",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }), 502


@app.route("/api/weather/bulletins", methods=["GET"])
def api_weather_bulletins():
    try:
        day = (request.args.get("date") or "").strip()
        conn = sqlite3.connect(WEATHER_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if day:
            cur.execute(
                """
                SELECT id, date, hour, temp, wind, humidity, pressure, wind_direction, condition, risk, score, status, bulletin, source, created_at, reliability_score, temp_variation, wind_variation
                FROM weather_bulletins
                WHERE date = ?
                ORDER BY hour DESC
                """,
                (day,),
            )
        else:
            cur.execute(
                """
                SELECT id, date, hour, temp, wind, humidity, pressure, wind_direction, condition, risk, score, status, bulletin, source, created_at, reliability_score, temp_variation, wind_variation
                FROM weather_bulletins
                ORDER BY date DESC, hour DESC
                LIMIT 24
                """
            )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({"ok": True, "count": len(rows), "bulletins": rows})
    except Exception as e:
        log.warning("api/weather/bulletins: %s", e)
        return jsonify({"ok": False, "error": str(e), "count": 0, "bulletins": []}), 500


@app.route("/api/weather/bulletins/latest", methods=["GET"])
def api_weather_bulletins_latest():
    try:
        conn = sqlite3.connect(WEATHER_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, date, hour, temp, wind, humidity, pressure, wind_direction, condition, risk, score, status, bulletin, source, created_at, reliability_score, temp_variation, wind_variation
            FROM weather_bulletins
            ORDER BY date DESC, hour DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"ok": True, "bulletin": None})
        return jsonify({"ok": True, "bulletin": dict(row)})
    except Exception as e:
        log.warning("api/weather/bulletins/latest: %s", e)
        return jsonify({"ok": False, "error": str(e), "bulletin": None}), 500


@app.route("/api/weather/history", methods=["GET"])
def api_weather_history():
    try:
        day = (request.args.get("date") or "").strip()
        if not day:
            day = datetime.now().strftime("%Y-%m-%d")

        _cleanup_weather_history_files()
        history_path = os.path.join(WEATHER_HISTORY_DIR, f"{day}.json")
        if os.path.isfile(history_path):
            with open(history_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            return jsonify({
                "ok": True,
                "date": payload.get("date", day),
                "temp": float(payload.get("temp", 0.0)),
                "wind": float(payload.get("wind", 0.0)),
                "humidity": int(payload.get("humidity", 0)),
                "pressure": float(payload.get("pressure", 1015)),
                "risk": payload.get("risk", "FAIBLE"),
                "source": "weather_history_json",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "archive": {
                    "saved": False,
                    "score": int(payload.get("score", 0)),
                    "status": payload.get("status", "STABLE"),
                    "bulletin": "",
                }
            })

        conn = sqlite3.connect(WEATHER_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT date, hour, temp, wind, humidity, pressure, wind_direction, condition, risk, score, status, bulletin,
                   reliability_score, temp_variation, wind_variation, source, created_at
            FROM weather_bulletins
            WHERE date = ?
            ORDER BY hour DESC
            LIMIT 1
            """,
            (day,),
        )
        row = cur.fetchone()
        conn.close()

        if row:
            item = dict(row)
            return jsonify({
                "ok": True,
                "temp": float(item.get("temp")),
                "wind": float(item.get("wind")),
                "humidity": int(item.get("humidity")),
                "pressure": float(item.get("pressure")),
                "wind_direction": float(item.get("wind_direction", 0.0)),
                "condition": item.get("condition") or "Unknown",
                "risk": item.get("risk") or "FAIBLE",
                "source": item.get("source") or "weather_bulletins",
                "updated_at": item.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "archive": {
                    "saved": False,
                    "score": int(item.get("score")) if item.get("score") is not None else None,
                    "status": item.get("status"),
                    "bulletin": item.get("bulletin"),
                    "reliability_score": item.get("reliability_score"),
                    "temp_variation": item.get("temp_variation"),
                    "wind_variation": item.get("wind_variation"),
                }
            })

        # Fallback live si historique absent
        weather_data = _build_local_weather_payload()
        archive_result = save_weather_bulletin(weather_data)
        weather_data["archive"] = archive_result
        return jsonify(weather_data)
    except Exception as e:
        log.warning("api/weather/history: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/weather/bulletins/save", methods=["POST"])
def api_weather_bulletins_save():
    try:
        payload = request.get_json(silent=True) or {}
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "payload invalide"}), 400
        if not all(k in data for k in ("temp", "wind", "humidity", "pressure", "wind_direction", "condition", "risk")):
            return jsonify({"ok": False, "error": "champs météo manquants"}), 400
        result = save_weather_bulletin(data)
        return jsonify({"ok": True, **result})
    except Exception as e:
        log.warning("api/weather/bulletins/save: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/apod")
def api_apod_alias():
    try:
        return api_nasa_apod()
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/api/oracle", methods=["POST"])
def api_oracle_alias():
    try:
        return api_oracle_cosmique()
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/api/aurores")
def api_aurores_alias():
    try:
        return api_aurore()
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route('/api/catalog')
def api_catalog():
    from modules.catalog import search_catalog
    q = request.args.get('q', '')
    t = request.args.get('type', '')
    return jsonify(get_cached('catalog_' + q + t, 86400, lambda: search_catalog(q, t)))


@app.route('/api/catalog/<obj_id>')
def api_catalog_object(obj_id):
    from modules.catalog import get_object
    obj = get_object(obj_id)
    if obj:
        return jsonify(obj)
    return jsonify({'error': 'Objet non trouvé'}), 404


@app.route('/api/tonight')
def api_tonight():
    from modules.observation_planner import get_tonight_objects
    return jsonify(get_cached('tonight', 3600, get_tonight_objects))


@app.route('/api/moon')
def api_moon():
    from modules.observation_planner import get_moon_phase
    return jsonify(get_moon_phase())


@app.route('/api/ephemerides/tlemcen')
def api_ephemerides_tlemcen():
    """Éphémérides du jour pour Tlemcen (34.88°N / 1.32°E / 800m) — cache 5 min."""
    cached = cache_get('eph_tlemcen', 300)
    if cached:
        return jsonify(cached)
    try:
        result = get_full_ephemeris()
        cache_set('eph_tlemcen', result)
        return jsonify(result)
    except Exception as e:
        log.warning("ephemerides/tlemcen error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/iss')
def api_v1_iss():
    from modules.orbit_engine import get_iss_precise, get_iss_crew
    data = get_iss_precise()
    if data.get("error"):
        return (
            jsonify(
                {
                    "object": "ISS",
                    "error": data.get("error"),
                    "position": None,
                    "crew": [],
                    "crew_count": 0,
                }
            ),
            503,
        )
    crew = get_iss_crew()
    sk = float(data.get("speed_kms", 7.66))
    return jsonify(
        {
            "object": "ISS",
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "position": {
                "latitude": data.get("lat", 0),
                "longitude": data.get("lon", 0),
                "altitude_km": data.get("alt_km", 408),
                "speed_kms": sk,
            },
            "velocity_kmh": round(sk * 3600.0, 1),
            "visibility": data.get("visibility", "nominal"),
            "orbits_today_estimate": data.get("orbits_today_estimate"),
            "orbital_period_min_approx": data.get("orbital_period_min_approx", 92),
            "crew": crew,
            "crew_count": len(crew) if isinstance(crew, list) else 0,
            "source": data.get("source", "Skyfield/SGP4"),
            "credit": "AstroScan-Chohra · ORBITAL-CHOHRA — https://astroscan.space",
        }
    )


@app.route('/api/v1/planets')
def api_v1_planets():
    """Positions héliocentriques temps réel via astropy. Cache 10 min."""
    cached = cache_get('v1_planets', 600)
    if cached is not None:
        return jsonify(cached)
    _PLANET_META = {
        'mercury': {'name': 'Mercure', 'diameter_km': 4879, 'moons': 0, 'type': 'Tellurique'},
        'venus':   {'name': 'Vénus',   'diameter_km': 12104,'moons': 0, 'type': 'Tellurique'},
        'earth':   {'name': 'Terre',   'diameter_km': 12742,'moons': 1, 'type': 'Tellurique'},
        'mars':    {'name': 'Mars',    'diameter_km': 6779, 'moons': 2, 'type': 'Tellurique'},
        'jupiter': {'name': 'Jupiter', 'diameter_km': 139820,'moons': 95,'type': 'Gazeuse'},
        'saturn':  {'name': 'Saturne', 'diameter_km': 116460,'moons': 146,'type': 'Gazeuse'},
        'uranus':  {'name': 'Uranus',  'diameter_km': 50724,'moons': 28, 'type': 'Gazeuse'},
        'neptune': {'name': 'Neptune', 'diameter_km': 49244,'moons': 16, 'type': 'Gazeuse'},
    }
    try:
        from astropy.coordinates import get_body_barycentric
        from astropy.time import Time
        import astropy.units as u
        t = Time.now()
        planets = []
        for body_key, meta in _PLANET_META.items():
            try:
                pos = get_body_barycentric(body_key, t)
                dist_au = float(pos.norm().to(u.au).value)
                x = float(pos.x.to(u.au).value)
                y = float(pos.y.to(u.au).value)
                z = float(pos.z.to(u.au).value)
            except Exception:
                dist_au = None; x = y = z = None
            row = dict(meta)
            row['distance_au'] = round(dist_au, 4) if dist_au is not None else None
            row['x_au'] = round(x, 4) if x is not None else None
            row['y_au'] = round(y, 4) if y is not None else None
            row['z_au'] = round(z, 4) if z is not None else None
            row['realtime'] = True
            planets.append(row)
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'astropy · DE432 ephemeris',
            'planets': planets,
            'credit': 'AstroScan-Chohra · ORBITAL-CHOHRA',
        }
        cache_set('v1_planets', payload)
        return jsonify(payload)
    except Exception as e:
        log.warning('api_v1_planets astropy: %s', e)
        fallback = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'fallback_static',
            'planets': [
                {'name':'Mercure','distance_au':0.39,'diameter_km':4879,'moons':0,'type':'Tellurique','realtime':False},
                {'name':'Vénus','distance_au':0.72,'diameter_km':12104,'moons':0,'type':'Tellurique','realtime':False},
                {'name':'Terre','distance_au':1.0,'diameter_km':12742,'moons':1,'type':'Tellurique','realtime':False},
                {'name':'Mars','distance_au':1.52,'diameter_km':6779,'moons':2,'type':'Tellurique','realtime':False},
                {'name':'Jupiter','distance_au':5.2,'diameter_km':139820,'moons':95,'type':'Gazeuse','realtime':False},
                {'name':'Saturne','distance_au':9.58,'diameter_km':116460,'moons':146,'type':'Gazeuse','realtime':False},
                {'name':'Uranus','distance_au':19.2,'diameter_km':50724,'moons':28,'type':'Gazeuse','realtime':False},
                {'name':'Neptune','distance_au':30.05,'diameter_km':49244,'moons':16,'type':'Gazeuse','realtime':False},
            ],
            'credit': 'AstroScan-Chohra · ORBITAL-CHOHRA',
        }
        return jsonify(fallback)


@app.route('/api/v1/catalog')
def api_v1_catalog():
    from modules.catalog import search_catalog
    q = request.args.get('q', '')
    return jsonify({
        'timestamp': __import__('datetime').datetime.utcnow().isoformat(),
        'query': q,
        'results': search_catalog(q),
        'credit': 'AstroScan-Chohra · ORBITAL-CHOHRA'
    })


@app.route('/api/microobservatory')
def api_microobservatory():
    targets = [
        {'name': 'M42 — Nébuleuse d\'Orion', 'ra': '05:35:17', 'dec': '-05:23:28', 'exposure': '60s'},
        {'name': 'M31 — Andromède', 'ra': '00:42:44', 'dec': '+41:16:09', 'exposure': '120s'},
        {'name': 'M13 — Amas Hercule', 'ra': '16:41:41', 'dec': '+36:27:41', 'exposure': '30s'},
        {'name': 'M57 — Nébuleuse Lyre', 'ra': '18:53:35', 'dec': '+33:01:45', 'exposure': '90s'},
    ]
    return jsonify({
        'service': 'MicroObservatory NASA — Harvard CfA',
        'url': 'https://mo-www.cfa.harvard.edu/OWN/',
        'targets': targets,
        'instructions': 'Connectez-vous sur MicroObservatory pour soumettre vos observations',
        'credit': 'AstroScan-Chohra · ORBITAL-CHOHRA'
    })


def _fetch_microobservatory_images():
    """
    Scrape recent images from Harvard MicroObservatory image directory.
    Keeps only entries that look recent (<= 10 days) when a date can be inferred.
    """
    base = "https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/"
    page_url = base + "ImageDirectory.php"
    now = datetime.now(timezone.utc)
    out = []
    try:
        html = _curl_get(page_url, timeout=20) or ""
        if not html:
            return {"ok": False, "images": [], "source": page_url, "error": "empty response"}

        def _format_object_name_from_filename(name):
            stem = (name or "").rsplit(".", 1)[0]
            # Extract object segment before first YYMMDD pattern.
            mdt = re.search(r"\d{6}", stem)
            obj_raw = stem[:mdt.start()] if mdt else stem
            obj_raw = obj_raw.replace("_", " ").replace("-", " ").strip()

            # Split CamelCase chunks.
            obj_raw = re.sub(r"([a-z])([A-Z])", r"\1 \2", obj_raw)

            # Normalize requested NGC/M patterns.
            # Example: NGC5457M101 -> NGC 5457 / M101
            m_nm = re.match(r"^\s*NGC\s*(\d+)\s*M\s*(\d+)\s*$", obj_raw, flags=re.I)
            if m_nm:
                obj_raw = f"NGC {m_nm.group(1)} / M{m_nm.group(2)}"
            else:
                obj_raw = re.sub(r"\bNGC(\d+)\b", r"NGC \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bIC(\d+)\b", r"IC \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bM(\d+)\b", r"M\1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bHD(\d+)\b", r"HD \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bHIP(\d+)\b", r"HIP \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bSAO(\d+)\b", r"SAO \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\s+", " ", obj_raw).strip()

            # Specific normalization requested.
            obj_raw = obj_raw.replace("T Coronae Bore", "T Coronae Borealis")
            if obj_raw.lower() == "t coronae bore":
                obj_raw = "T Coronae Borealis"
            return obj_raw or "Unknown object"

        def _parse_date_obs_from_filename(name):
            stem = (name or "").rsplit(".", 1)[0]
            # YYMMDDHHMMSS
            m = re.search(r"(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", stem)
            if not m:
                return None
            yy, mo, dd, hh, mi, ss = m.groups()
            try:
                if not (1 <= int(mo) <= 12 and 1 <= int(dd) <= 31 and 0 <= int(hh) <= 23 and 0 <= int(mi) <= 59 and 0 <= int(ss) <= 59):
                    return None
            except Exception:
                return None
            return f"{yy}/{mo}/{dd} {hh}:{mi}:{ss} UTC"

        # Extract candidate image URLs from href/src.
        # Keep only FITS/FIT/JPG families (requested).
        link_re = re.compile(r'''(?:href|src)=["']([^"']+\.(?:fits|fit|jpg|jpeg))["']''', re.I)
        candidates = link_re.findall(html)

        # Also try generic absolute URLs in text.
        abs_re = re.compile(r'''https?://[^\s"'<>]+\.(?:fits|fit|jpg|jpeg)''', re.I)
        candidates.extend(abs_re.findall(html))

        seen = set()
        for raw in candidates:
            url = raw.strip()
            if not url:
                continue
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = base.rstrip("/") + url
            elif not url.lower().startswith("http"):
                url = base + url
            if url in seen:
                continue
            seen.add(url)

            name = url.split("/")[-1] or "image"
            lname = name.lower()

            # Exclusion criteria for UI/non-astronomical assets.
            excluded_tokens = ["icon", "logo", "crop", "observatory2300", "fits_icon"]
            if any(tok in lname for tok in excluded_tokens):
                continue

            # Keep only requested extensions explicitly.
            if not (lname.endswith(".fits") or lname.endswith(".fit") or lname.endswith(".jpg") or lname.endswith(".jpeg")):
                continue

            # Keep only names likely tied to astronomical objects.
            # Accept common catalogs/designators (M, NGC, IC, HD, HIP, SAO, Messier, Nebula, Galaxy, etc.).
            astro_name_re = re.compile(
                r'(?:^|[_\-\s])('
                r'm\d{1,3}|ngc\d{1,4}|ic\d{1,4}|hd\d{1,6}|hip\d{1,6}|sao\d{1,6}|'
                r'iss|j\d{4,}|'
                r'andromeda|orion|nebula|galaxy|cluster|pleiades|vega|sirius|'
                r'jupiter|saturn|mars|moon|luna|sun|solar|comet|asteroid'
                r')',
                re.I
            )
            if not astro_name_re.search(lname):
                continue

            # Try to infer date from URL patterns: YYYYMMDD or YYYY-MM-DD.
            date_obj = None
            m1 = re.search(r"(20\d{2})(\d{2})(\d{2})", url)
            m2 = re.search(r"(20\d{2})-(\d{2})-(\d{2})", url)
            try:
                if m2:
                    y, mo, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
                    date_obj = datetime(y, mo, d, tzinfo=timezone.utc)
                elif m1:
                    y, mo, d = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
                    date_obj = datetime(y, mo, d, tzinfo=timezone.utc)
            except Exception:
                date_obj = None

            # Keep only <=10 days if date is known.
            if date_obj is not None:
                age_days = (now - date_obj).days
                if age_days < 0 or age_days > 10:
                    continue

            obj = _format_object_name_from_filename(name)
            date_obs = _parse_date_obs_from_filename(name)
            out.append({
                "nom": name,
                "url": url,
                "objet": obj,
                "date": date_obj.isoformat().replace("+00:00", "Z") if date_obj else None,
                "date_obs": date_obs,
            })

        # Sort by date desc when available; unknown dates last.
        out.sort(key=lambda x: (x["date"] is None, x["date"] or ""), reverse=False)
        out = out[:30]
        return {"ok": True, "images": out, "source": page_url, "count": len(out)}
    except Exception as e:
        log.warning("microobservatory/images scrape: %s", e)
        return {"ok": False, "images": [], "source": page_url, "error": str(e)}


@app.route('/api/microobservatory/images')
def api_microobservatory_images():
    """Recent Harvard MicroObservatory images (cached 3600s)."""
    try:
        data = get_cached('microobservatory_images', 3600, _fetch_microobservatory_images)
        return jsonify(data if isinstance(data, dict) else {"ok": False, "images": []})
    except Exception as e:
        return jsonify({"ok": False, "images": [], "error": str(e)})


@app.route('/api/microobservatory/preview/<nom_fichier>')
def api_microobservatory_preview(nom_fichier):
    """
    Download FITS from Harvard MicroObservatory, convert to JPG and return it.
    Uses local file cache to avoid repeated conversions.
    """
    try:
        safe_name = secure_filename(nom_fichier or "")
        if not safe_name:
            return jsonify({"ok": False, "error": "invalid filename"}), 400

        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in (".fits", ".fit"):
            return jsonify({"ok": False, "error": "preview supports FITS only"}), 400

        preview_dir = os.path.join(STATION, "data", "microobservatory_previews")
        fits_dir = os.path.join(preview_dir, "fits")
        jpg_dir = os.path.join(preview_dir, "jpg")
        os.makedirs(fits_dir, exist_ok=True)
        os.makedirs(jpg_dir, exist_ok=True)

        fits_path = os.path.join(fits_dir, safe_name)
        jpg_name = os.path.splitext(safe_name)[0] + ".jpg"
        jpg_path = os.path.join(jpg_dir, jpg_name)

        # Serve cached JPG when possible.
        if os.path.isfile(jpg_path) and os.path.getsize(jpg_path) > 0:
            return send_file(jpg_path, mimetype="image/jpeg")

        source_url = "https://mo-www.cfa.harvard.edu/ImageDirectory/" + safe_name

        # Download FITS file.
        import urllib.request
        req = urllib.request.Request(source_url, headers={"User-Agent": "AstroScan/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if not data:
            return jsonify({"ok": False, "error": "empty FITS download"}), 502
        with open(fits_path, "wb") as f:
            f.write(data)

        # Convert FITS to JPG.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from astropy.io import fits
        import numpy as np

        arr = fits.getdata(fits_path)
        if arr is None:
            return jsonify({"ok": False, "error": "invalid FITS data"}), 502

        # Reduce dimensions if needed.
        while hasattr(arr, "ndim") and arr.ndim > 2:
            arr = arr[0]
        arr = np.asarray(arr, dtype=float)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        if arr.size == 0:
            return jsonify({"ok": False, "error": "empty FITS array"}), 502

        # Robust contrast stretch (2-98 percentile).
        vmin = np.percentile(arr, 2)
        vmax = np.percentile(arr, 98)
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            vmin = float(np.min(arr))
            vmax = float(np.max(arr)) if float(np.max(arr)) > float(np.min(arr)) else float(np.min(arr)) + 1.0

        plt.figure(figsize=(8, 8), dpi=120)
        plt.imshow(arr, cmap="gray", origin="lower", vmin=vmin, vmax=vmax)
        plt.axis("off")
        plt.tight_layout(pad=0)
        plt.savefig(jpg_path, format="jpg", bbox_inches="tight", pad_inches=0)
        plt.close()

        if not os.path.isfile(jpg_path) or os.path.getsize(jpg_path) == 0:
            return jsonify({"ok": False, "error": "jpg conversion failed"}), 502
        return send_file(jpg_path, mimetype="image/jpeg")
    except Exception as e:
        log.warning("microobservatory/preview: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


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


def _telescope_nightly_tlemcen():
    """
    Pipeline nocturne complet :
    1. Scan répertoire Harvard MicroObservatory
    2. Sélection 3 objets visibles depuis Tlemcen (altitude > 20° à 23h00 UTC)
    3. Téléchargement FITS + conversion JPG
    4. Sauvegarde métadonnées nightly_meta.json
    """
    import urllib.request
    from datetime import timedelta

    log.info('telescope_nightly: démarrage pipeline — Tlemcen 34.87°N 1.32°E')

    try:
        mo_catalog = _mo_fetch_catalog_today()
    except Exception as e:
        log.error('telescope_nightly: catalog error: %s', e)
        mo_catalog = {}

    try:
        visible = _mo_visible_tonight()
        log.info('telescope_nightly: %d objets visibles', len(visible))
    except Exception as e:
        log.error('telescope_nightly: visibility error: %s', e)
        visible = []

    results = []
    used_labels = set()

    for obj in visible:
        if len(results) >= 3:
            break
        label = obj['label']
        if label in used_labels:
            continue

        entries = mo_catalog.get(obj['prefix'], [])
        if not entries:
            log.debug('telescope_nightly: %s — aucun FITS MO disponible', obj['prefix'])
            continue

        entry = entries[0]  # Le plus récent
        fits_url = entry['url']
        captured_at = entry['captured_at']

        try:
            req = urllib.request.Request(fits_url, headers={'User-Agent': 'AstroScan-Chohra/2.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                fits_bytes = r.read()
            if len(fits_bytes) < 2880:  # FITS minimum = 1 bloc de 2880 octets
                log.warning('telescope_nightly: %s FITS trop petit (%d o)', obj['prefix'], len(fits_bytes))
                continue

            safe_stem = re.sub(r'[^\w]', '_', os.path.splitext(entry['filename'])[0])
            jpg_name  = f"nightly_{safe_stem}.jpg"
            jpg_path  = os.path.join(STATION, 'telescope_live', jpg_name)

            hdr_date = _mo_fits_to_jpg(fits_bytes, jpg_path)

            results.append({
                'object_label':       obj['label'],
                'object_type':        obj['type'],
                'object_prefix':      obj['prefix'],
                'altitude_deg':       obj['alt'],
                'filename_fits':      entry['filename'],
                'jpg':                jpg_name,
                'fits_url':           fits_url,
                'captured_at_utc':    captured_at.isoformat(),
                'captured_at_display': captured_at.strftime('%d/%m/%Y %H:%M UTC'),
                'obs_date_header':    hdr_date or '',
                'source':             'Harvard MicroObservatory · CfA · Cambridge MA',
                'telescope_aperture': '6 pouces (152 mm)',
                'fetched_at':         datetime.now(timezone.utc).isoformat(),
            })
            used_labels.add(label)
            log.info('telescope_nightly: ✓ %s — alt=%.1f° — capturé %s',
                     obj['label'], obj['alt'], captured_at.strftime('%d/%m/%Y %H:%M UTC'))

        except Exception as e:
            log.warning('telescope_nightly: %s → skipped: %s', obj['prefix'], e)

    meta = {
        'run_at':       datetime.now(timezone.utc).isoformat(),
        'run_date':     datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'location':     {'city': 'Tlemcen', 'lat': 34.87, 'lon': 1.32, 'alt_m': 816},
        'source':       'Harvard MicroObservatory — waps.cfa.harvard.edu',
        'note':         'FITS originaux · Télescopes robotiques CCD 6" · Pipeline automatique AstroScan',
        'total_visible_tonight': len(visible),
        'images':       results,
    }
    meta_path = os.path.join(STATION, 'telescope_live', 'nightly_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)

    cache_set('mo_catalog_today', None)
    log.info('telescope_nightly: terminé — %d image(s) collectée(s)', len(results))
    return meta


@app.route('/api/telescope/nightly')
def api_telescope_nightly():
    """Images nocturnes Harvard MicroObservatory — sélection Tlemcen."""
    meta_path = os.path.join(STATION, 'telescope_live', 'nightly_meta.json')
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding='utf-8') as f:
                data = json.load(f)
            data['ok'] = True
            return jsonify(data)
        except Exception:
            pass
    return jsonify({'ok': False, 'images': [], 'message': 'Aucune collecte nocturne disponible'})


@app.route('/api/telescope/trigger-nightly', methods=['POST'])
def api_telescope_trigger_nightly():
    """Déclenche manuellement le pipeline nocturne Harvard MO."""
    import threading
    t = threading.Thread(target=_telescope_nightly_tlemcen, daemon=True)
    t.start()
    return jsonify({'ok': True, 'message': 'Pipeline nocturne démarré en arrière-plan'})


@app.route('/telescope_live/<path:filename>')
def serve_telescope_live_img(filename):
    """Sert les JPG nightly convertis depuis FITS Harvard."""
    safe = secure_filename(filename)
    path = os.path.join(STATION, 'telescope_live', safe)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype='image/jpeg')


@app.route('/mission-control')
def mission_control():
    return render_template('mission_control.html', cesium_token=CESIUM_TOKEN)


@app.route('/api/mission-control')
def api_mission_control():
    try:
        from modules.mission_control import get_global_mission_status
        return jsonify(get_global_mission_status())
    except Exception as e:
        log.warning('api/mission-control: %s', e)
        return jsonify({'error': str(e), 'iss': {}, 'mars': {}, 'neo': {}, 'voyager': {}}), 500


@app.route('/api/astro/object', methods=['GET', 'POST'])
def api_astro_object():
    """Explication d'un objet céleste par nom (modules.astro_ai.explain_object)."""
    name = request.args.get('name') or (request.get_json(silent=True) or {}).get('name') or ''
    try:
        from modules.astro_ai import explain_object
        return jsonify(explain_object(name))
    except Exception as e:
        log.warning('api/astro/object: %s', e)
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/news')
def api_news():
    try:
        from modules.news_module import get_live_news
        articles = get_live_news()
        data = {'articles': articles, 'count': len(articles), 'source': 'live'}
    except Exception as e:
        data = {'ok': False, 'error': str(e)}
    return jsonify(data)

# ── API SDR Passes (prédictions NOAA, TLE CelesTrak, cache 2h, Tlemcen) ──
# MIGRATED TO sdr_bp 2026-05-02 — see app/blueprints/sdr/routes.py
# @app.route('/api/sdr/passes')
# def api_sdr_passes():
#     return api_sdr_passes_impl(
#         jsonify=jsonify,
#         STATION=STATION,
#         Path=Path,
#         json_module=json,
#         time_module=time,
#         subprocess_module=subprocess,
#         log=log,
#     )

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


@app.route('/api/v1/asteroids')
def api_v1_asteroids():
    from modules.space_alerts import get_asteroid_alerts
    data = get_cached('asteroids', 3600, get_asteroid_alerts)
    return jsonify({
        'timestamp': __import__('datetime').datetime.utcnow().isoformat(),
        'total_today': data.get('total_today', 0) if data else 0,
        'hazardous': data.get('alerts', []) if data else [],
        'source': 'NASA NeoWs',
        'credit': 'AstroScan-Chohra · ORBITAL-CHOHRA'
    })


@app.route('/api/v1/solar-weather')
def api_v1_solar():
    from modules.space_alerts import get_solar_weather
    data = get_cached('solar_weather', 300, get_solar_weather)
    return jsonify({
        'timestamp': __import__('datetime').datetime.utcnow().isoformat(),
        'solar_wind': data or {},
        'source': 'NOAA SWPC',
        'credit': 'AstroScan-Chohra · ORBITAL-CHOHRA'
    })


@app.route('/api/v1/tonight')
def api_v1_tonight():
    from modules.observation_planner import get_tonight_objects
    return jsonify({
        'timestamp': __import__('datetime').datetime.utcnow().isoformat(),
        'location': 'Tlemcen, Algérie (~34,9°N, 1,3°E)',
        'data': get_cached('tonight', 3600, get_tonight_objects),
        'credit': 'AstroScan-Chohra · ORBITAL-CHOHRA'
    })


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

@app.route('/api/feeds/voyager')
def api_feeds_voyager():
    data = get_cached('voyager', 3600, _fetch_voyager)
    if not data:
        now = _dt_utc.utcnow()
        days_v1 = (now - _dt_utc(1977, 9, 5)).days
        days_v2 = (now - _dt_utc(1977, 8, 20)).days
        v1_au = 17.0 + days_v1 * 0.000985
        v2_au = 14.5 + days_v2 * 0.000898
        data = {
            'VOYAGER_1': {'dist_au': round(v1_au, 2), 'dist_km': round(v1_au * 149597870.7), 'speed_km_s': 17.0, 'source': 'Calcul approx.'},
            'VOYAGER_2': {'dist_au': round(v2_au, 2), 'dist_km': round(v2_au * 149597870.7), 'speed_km_s': 15.4, 'source': 'Calcul approx.'},
        }
    return jsonify({'ok': True, 'data': data})

@app.route('/api/feeds/neo')
def api_feeds_neo():
    data = get_cached('neo', 3600, _fetch_neo)
    return jsonify({'ok': True, 'neos': data or [], 'count': len(data) if data else 0})

@app.route('/api/feeds/solar')
def api_feeds_solar():
    data = get_cached('solar', 900, _fetch_solar_wind)
    return jsonify({'ok': True, 'solar_wind': data})

@app.route('/api/feeds/solar_alerts')
def api_feeds_solar_alerts():
    """Alertes éruptions solaires et flares X-ray — NOAA SWPC."""
    data = get_cached('solar_alerts', 600, _fetch_solar_alerts)
    return jsonify({'ok': True, 'alerts': data.get('alerts', []) if data else [], 'flares': data.get('flares', []) if data else []})

@app.route('/api/feeds/mars')
def api_feeds_mars():
    data = get_cached('mars', 7200, _fetch_mars_rover)
    return jsonify({'ok': True, 'photos': data or []})

@app.route('/api/sondes')
def api_sondes():
    """Agrégation SONDES SPATIALES — logique dans sondes_module.py."""
    try:
        import sys
        if STATION not in sys.path:
            sys.path.insert(0, STATION)
        from modules.sondes_module import get_sondes_payload
        return jsonify(get_sondes_payload())
    except Exception as e:
        log.warning('api_sondes: %s', e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/feeds/apod_hd')
def api_feeds_apod_hd():
    """NASA APOD. Cache 3600 s pour limiter les appels externes."""
    cache_cleanup()
    cached = cache_get("apod_hd", 3600)
    if cached is not None:
        return jsonify(cached)
    data = get_cached('apod_hd', 3600, _fetch_apod_hd)
    payload = {'ok': True, 'apod': data}
    cache_set("apod_hd", payload)
    return jsonify(payload)

@app.route('/api/feeds/all')
def api_feeds_all():
    """Tous les feeds en un appel (Voyager JPL, NEO, vent solaire, alertes solaires, Mars, APOD)."""
    return jsonify({
        'ok': True,
        'voyager': get_cached('voyager', 3600, _fetch_voyager),
        'neo': get_cached('neo', 3600, _fetch_neo),
        'solar_wind': get_cached('solar', 900, _fetch_solar_wind),
        'solar_alerts': get_cached('solar_alerts', 600, _fetch_solar_alerts),
        'mars': get_cached('mars', 7200, _fetch_mars_rover),
        'apod_hd': get_cached('apod_hd', 3600, _fetch_apod_hd),
        'station': 'ORBITAL-CHOHRA · Tlemcen, Algérie',
        'timestamp': _dt_utc.utcnow().isoformat(),
    })

# ── Health check ──
@app.route('/api/health')
def api_health():
    total, anom, sources = 0, 0, []
    uptime_str = '—'
    try:
        conn = sqlite3.connect('/root/astro_scan/data/archive_stellaire.db', timeout=10.0)
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anom  = conn.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
        rows  = conn.execute("SELECT DISTINCT source FROM observations WHERE timestamp > datetime('now','-7 days')").fetchall()
        sources = [r[0] for r in rows]
        last  = conn.execute("SELECT COALESCE(title,objets_detectes,'') as t, timestamp FROM observations ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
    except: pass
    try:
        uptime_str = open('/proc/uptime').read().split()[0]
        s = int(float(uptime_str))
        uptime_str = f"{s//3600}h {(s%3600)//60}m"
    except: pass
    import os
    payload = {
        'ok': True, 'station': 'ORBITAL-CHOHRA',
        'ip': '5.78.153.17', 'location': 'Tlemcen, Algérie',
        'director': 'Zakaria Chohra — Tlemcen, Algérie',
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'uptime': uptime_str,
        'db': {'total': total, 'anomalies': anom, 'sources': sources},
        'services': {
            'gemini': 'active' if os.environ.get('GEMINI_API_KEY') else 'missing',
            'grok':   'inactive',
            'groq':   'active' if os.environ.get('GROQ_API_KEY')   else 'missing',
            'nasa':   'active' if os.environ.get('NASA_API_KEY')    else 'missing',
            'aegis': 'active', 'sdr': 'active', 'iss': 'active'
        },
        'coordinates': {'lat': 34.87, 'lon': 1.32, 'alt_m': 800, 'timezone': 'Africa/Algiers'}
    }
    # Champs opérationnels additifs (monitoring / V2) — ne modifient pas les clés historiques ci-dessus
    try:
        if _core_status_engine is not None:
            payload['operational'] = _core_status_engine.build_operational_health(
                STATION,
                DB_PATH,
                TLE_CACHE,
                TLE_CACHE_FILE,
                ws_present=True,
                sse_present=True,
            )
            payload['data_credibility'] = _core_status_engine.data_credibility_stub(TLE_CACHE, TLE_CACHE_FILE)
    except Exception as ex:
        log.debug("api_health operational: %s", ex)
        try:
            payload['operational'] = {'status': 'unknown', 'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'error': 'probe_partial'}
        except Exception:
            pass
    return jsonify(payload)




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


@app.route('/status')
def api_status():
    """
    GET /status
    Snapshot JSON stable pour badges UI / monitoring (pas d'appels réseau bloquants).
    """
    return jsonify(build_status_snapshot_dict())


@app.route("/stream/status")
def stream_status_sse():
    """
    Flux SSE additif : même snapshot que /status, toutes les ~3 s.
    Alternative stable au WebSocket pour Gunicorn multi-workers (pas de retrait de /ws/status).
    """
    def _gen():
        while True:
            try:
                snap = build_status_snapshot_dict()
                yield "data: " + json.dumps(snap, default=str) + "\n\n"
            except Exception as ex:
                try:
                    yield "data: " + json.dumps({"error": str(ex)[:200], "stream": "status"}) + "\n\n"
                except Exception:
                    pass
            time.sleep(3)

    return Response(
        stream_with_context(_gen()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

@app.route("/telescopes")
def telescopes():
    return render_template("telescopes.html")


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


_JWST_STATIC = [
    {
        'title': 'Pillars of Creation — NIRCam',
        'url': 'https://stsci-opo.org/STScI-01GA6KKWG5388N7P9NWJGQFQ3E.png',
        'date': '2022-10-19',
        'credits': 'NASA/ESA/CSA JWST · STScI',
        'description': 'Les Piliers de la Création photographiés par le NIRCam de JWST révèlent des colonnes de gaz et de poussière interstellaire où naissent de nouvelles étoiles dans la nébuleuse de l\'Aigle (M16). Cette image infrarouge perce les voiles de poussière et expose des milliers d\'étoiles en formation jamais visibles auparavant.',
    },
    {
        'title': 'Carina Nebula — NIRCam',
        'url': 'https://stsci-opo.org/STScI-01G7ETPF7T11KYRNMQXFD9YHHK.png',
        'date': '2022-07-12',
        'credits': 'NASA/ESA/CSA JWST · STScI',
        'description': 'La Nébuleuse de la Carène vue par JWST en infrarouge proche dévoile des centaines de proto-étoiles et d\'étoiles jeunes enfouies dans les nuages de gaz moléculaires. Cette région de formation stellaire intense, située à 7 600 années-lumière, révèle pour la première fois les contours précis des «falaises cosmiques» d\'où émergent de nouvelles étoiles.',
    },
    {
        'title': 'SMACS 0723 — Premier champ profond',
        'url': 'https://stsci-opo.org/STScI-01G77PKB8NKR7S8Z3HN3KVTF21.png',
        'date': '2022-07-12',
        'credits': 'NASA/ESA/CSA JWST · STScI',
        'description': 'Le premier champ profond de JWST centré sur l\'amas de galaxies SMACS 0723 montre des milliers de galaxies sur un timbre-poste de ciel. La gravité de l\'amas agit comme une lentille gravitationnelle qui amplifie et déforme la lumière de galaxies encore plus lointaines, certaines vieilles de plus de 13 milliards d\'années.',
    },
    {
        'title': 'Stephan\'s Quintet — NIRCam+MIRI',
        'url': 'https://stsci-opo.org/STScI-01G7QAGTDMTB1RYQE9P5AXH3HZ.png',
        'date': '2022-07-12',
        'credits': 'NASA/ESA/CSA JWST · STScI',
        'description': 'Le Quintette de Stephan, premier groupe compact de galaxies découvert, montre quatre des cinq galaxies en interaction gravitationnelle intense dans cette mosaïque JWST de 150 millions de pixels. Les ondes de choc issues des collisions galactiques et les flots de gaz sont clairement visibles, offrant une fenêtre unique sur l\'évolution des galaxies.',
    },
    {
        'title': 'Southern Ring Nebula — NIRCam',
        'url': 'https://stsci-opo.org/STScI-01G6DCYD09HESZR8CNAQFWCN3K.png',
        'date': '2022-07-12',
        'credits': 'NASA/ESA/CSA JWST · STScI',
        'description': 'La Nébuleuse de l\'Anneau du Sud (NGC 3132) révèle une étoile mourante en train d\'expulser ses couches externes dans l\'espace. JWST identifie clairement l\'étoile blanche centrale responsable des anneaux de gaz lumineux, dévoilant la structure complexe de cette nébuleuse planétaire située à 2 000 années-lumière dans la constellation des Voiles.',
    },
    {
        'title': 'Tarantula Nebula — NIRCam',
        'url': 'https://stsci-opo.org/STScI-01GE6XCSMFB1XHZS8ZJNRKX0WN.png',
        'date': '2022-09-06',
        'credits': 'NASA/ESA/CSA JWST · STScI',
        'description': 'La Nébuleuse de la Tarentule (30 Doradus), région de formation stellaire la plus active et lumineuse des galaxies satellites de la Voie Lactée, est photographiée ici par JWST. Les filaments de gaz ionisé entourent des amas d\'étoiles massives ultra-brillantes dont les vents stellaires sculptent les cavités de la nébuleuse.',
    },
]

_JWST_CACHE_FILE = '/root/astro_scan/data/jwst_cache.json'
_JWST_CACHE_TTL = 21600  # 6 heures


def _fetch_jwst_live_images():
    """Fetch JWST images: NASA images API → file cache → static fallback."""
    import time as _t
    # 1. File cache (6h)
    try:
        if os.path.exists(_JWST_CACHE_FILE):
            age = _t.time() - os.path.getmtime(_JWST_CACHE_FILE)
            if age < _JWST_CACHE_TTL:
                with open(_JWST_CACHE_FILE, 'r') as f:
                    cached = json.load(f)
                    if cached:
                        return cached
    except Exception:
        pass

    imgs = []

    # 2. NASA Images API — JWST science images (post-launch 2022+)
    try:
        raw = _curl_get(
            'https://images-api.nasa.gov/search?q=webb+telescope+nebula+galaxy&media_type=image&year_start=2022',
            timeout=12
        )
        if raw:
            data = json.loads(raw)
            items = data.get('collection', {}).get('items', [])
            science_imgs = []
            for item in items:
                meta = item.get('data', [{}])[0]
                links = item.get('links', [{}])
                img_url = links[0].get('href', '') if links else ''
                date = (meta.get('date_created') or '')[:10]
                # Only science images (post first-light)
                if img_url and meta.get('title') and date >= '2022-07-01':
                    science_imgs.append({
                        'title': meta.get('title', 'JWST Image'),
                        'url': img_url,
                        'date': date,
                        'credits': 'NASA/ESA/CSA JWST',
                        'description': '',
                    })
                if len(science_imgs) >= 6:
                    break
            if len(science_imgs) >= 4:
                imgs = science_imgs
    except Exception:
        pass

    # Use static if live results insufficient
    if len(imgs) < 4:
        imgs = list(_JWST_STATIC)

    # 3. Claude AI analysis for each image (up to 4)
    nasa_key_env = (os.environ.get('NASA_API_KEY') or 'DEMO_KEY').strip()
    for img in imgs[:4]:
        if img.get('description'):
            continue
        try:
            prompt = (
                f"En exactement 2 phrases en français (sans titre, sans markdown, sans numérotation), "
                f"décris scientifiquement l'image JWST intitulée '{img['title']}' ({img.get('date','')}) "
                f"pour un public passionné d'astronomie. Commence directement par la description."
            )
            desc, err = _call_claude(prompt)
            if desc and not err:
                # Strip any markdown headers
                lines = [l for l in desc.strip().split('\n') if l.strip() and not l.startswith('#')]
                img['description'] = ' '.join(lines).strip()
        except Exception:
            pass

    # 4. Save to file cache
    try:
        with open(_JWST_CACHE_FILE, 'w') as f:
            json.dump(imgs, f)
    except Exception:
        pass

    return imgs


def _fetch_jwst():
    """Compat wrapper."""
    return _fetch_jwst_live_images()


@app.route('/api/hubble/images')
def api_hubble_images():
    """Proxy Hubble images — ESA API ou fallback statique."""
    try:
        return jsonify(_fetch_hubble())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mars/weather')
def api_mars_weather():
    """InSight météo Mars — proxy JSON (mission terminée, peut être vide)."""
    try:
        url = 'https://api.nasa.gov/insight_weather/?api_key={}&feedtype=json&ver=1.0'.format(os.environ.get('NASA_API_KEY','DEMO_KEY'))
        raw = _curl_get(url, timeout=10)
        if not raw:
            return jsonify({'error': 'no data'}), 502
        return app.response_class(raw, mimetype='application/json')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bepi/telemetry')
def api_bepi():
    """BepiColombo — synthèse + tentative JPL Horizons."""
    out = {
        'status': 'EN ROUTE VERS MERCURE',
        'agence': 'ESA/JAXA',
        'lancement': '2018',
        'arrivee': '2025',
        'name': 'BepiColombo',
    }
    try:
        raw = _curl_get(
            'https://ssd.jpl.nasa.gov/api/horizons.api?format=text&COMMAND=-121&OBJ_DATA=YES'
            '&MAKE_EPHEM=YES&EPHEM_TYPE=VECTORS&CENTER=500@10&START_TIME=today&STOP_TIME=today&STEP_SIZE=1d&QUANTITIES=20',
            timeout=12,
        )
        if raw:
            out['raw'] = raw[:500]
    except Exception as e:
        out['error'] = str(e)
    return jsonify(out)


@app.route('/api/jwst/images')
def api_jwst_images():
    """Images JWST — NASA Images API + Claude AI descriptions + fallback statique."""
    try:
        data = _fetch_jwst_live_images()
        if not data:
            return jsonify({'error': 'no data'}), 502
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jwst/refresh', methods=['POST'])
def api_jwst_refresh():
    """Force le rechargement du cache JWST."""
    try:
        if os.path.exists(_JWST_CACHE_FILE):
            os.remove(_JWST_CACHE_FILE)
        data = _fetch_jwst_live_images()
        return jsonify({'ok': True, 'count': len(data)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/neo')
def api_neo():
    import urllib.request, json
    from datetime import datetime, timedelta
    try:
        nasa_key = os.environ.get('NASA_API_KEY', 'DEMO_KEY')
        today = datetime.utcnow().strftime('%Y-%m-%d')
        tomorrow = (datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%d')
        url = f'https://api.nasa.gov/neo/rest/v1/feed?start_date={today}&end_date={tomorrow}&api_key={nasa_key}'
        req = urllib.request.Request(url, headers={'User-Agent':'AstroScan/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        neos = []
        for date, asteroids in data.get('near_earth_objects', {}).items():
            for a in asteroids:
                neos.append({
                    'nom': a['name'],
                    'date': date,
                    'diametre_min': round(a['estimated_diameter']['kilometers']['estimated_diameter_min'], 3),
                    'diametre_max': round(a['estimated_diameter']['kilometers']['estimated_diameter_max'], 3),
                    'vitesse_kms': round(float(a['close_approach_data'][0]['relative_velocity']['kilometers_per_second']), 2),
                    'distance_km': round(float(a['close_approach_data'][0]['miss_distance']['kilometers'])),
                    'dangereux': a['is_potentially_hazardous_asteroid'],
                    'url': a['nasa_jpl_url']
                })
        neos.sort(key=lambda x: x['distance_km'])
        return jsonify({'count': len(neos), 'asteroids': neos[:20], 'generated_at': today})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/nasa/apod')
def api_nasa_apod():
    """Image du jour NASA (APOD)."""
    try:
        payload = get_cached('nasa_apod_v1', 1800, _fetch_nasa_apod)
        code = 200 if payload.get("ok") else 502
        return jsonify(payload), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# MIGRATED TO apod_bp 2026-05-02 — see app/blueprints/apod/routes.py
# @app.route("/apod")
# def apod_fr_json():
#     return apod_fr_json_impl(jsonify=jsonify, log=log)


# MIGRATED TO apod_bp 2026-05-02 — see app/blueprints/apod/routes.py
# @app.route("/apod/view")
# def apod_fr_view():
#     return apod_fr_view_impl(render_template=render_template, log=log)


# MIGRATED TO apod_bp 2026-05-02 — see app/blueprints/apod/routes.py
# @app.route("/nasa-apod")
# def page_nasa_apod():
#     return render_template("nasa_apod.html")


@app.route('/api/nasa/neo')
def api_nasa_neo():
    """Objets proches de la Terre (NASA NEO)."""
    try:
        payload = get_cached('nasa_neo_v1', 900, _fetch_nasa_neo)
        code = 200 if payload.get("ok") else 502
        return jsonify(payload), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "asteroids": []}), 500


@app.route('/api/nasa/solar')
def api_nasa_solar():
    """Météo solaire NASA DONKI."""
    try:
        payload = get_cached('nasa_solar_v1', 600, _fetch_nasa_solar)
        code = 200 if payload.get("ok") else 502
        return jsonify(payload), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "events": []}), 500


@app.route('/api/alerts/asteroids')
def api_asteroids():
    from modules.space_alerts import get_asteroid_alerts
    return jsonify(get_cached('asteroids', 3600, get_asteroid_alerts))


@app.route('/api/alerts/solar')
def api_solar():
    from modules.space_alerts import get_solar_weather
    return jsonify(get_cached('solar_weather', 300, get_solar_weather))


@app.route('/api/alerts/all')
def api_alerts_all():
    from modules.space_alerts import get_asteroid_alerts, get_solar_weather
    return jsonify({
        'asteroids': get_cached('asteroids', 3600, get_asteroid_alerts),
        'solar': get_cached('solar_weather', 300, get_solar_weather),
        'timestamp': __import__('datetime').datetime.utcnow().isoformat()
    })


@app.route('/api/live/spacex')
def api_spacex():
    from modules.live_feeds import get_spacex_launches
    return jsonify(get_cached('spacex', 3600, get_spacex_launches))


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


@app.route('/api/live/news')
def api_space_news():
    """News spatiales — titres/résumés avec remplacement manuel de termes fréquents."""
    from modules.live_feeds import get_space_news
    def _get():
        items = get_space_news()
        return _apply_news_translations(items)
    return jsonify(get_cached('space_news', 1800, _get))


@app.route('/api/live/mars-weather')
def api_live_mars_weather():
    from modules.live_feeds import get_mars_weather
    return jsonify(get_cached('mars_weather', 3600, get_mars_weather))


@app.route('/api/live/iss-passes')
def api_live_iss_passes():
    from modules.live_feeds import get_iss_passes_tlemcen
    # Fenêtre plus courte que 1 h : les fenêtres de passage ISS évoluent vite.
    return jsonify(get_cached('iss_passes', 600, get_iss_passes_tlemcen))


def _az_to_direction(az_deg):
    """Convert azimuth degrees to compass direction (8-point)."""
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    return dirs[int((az_deg + 22.5) / 45) % 8]


def _compute_iss_passes_for_observer(lat_deg, lon_deg):
    """
    Calcule les 5 prochains passages ISS pour un observateur (lat/lon °, WGS84)
    via SGP4 + TLE local. Format enrichi (azimut, visibilité).
    """
    import math
    import datetime as _dt

    LAT_DEG, LON_DEG = float(lat_deg), float(lon_deg)
    Re = 6371.0

    def xyz_observer(lat, lon):
        return (Re * math.cos(lat) * math.cos(lon),
                Re * math.cos(lat) * math.sin(lon),
                Re * math.sin(lat))

    def el_az(sat_xyz, obs_lat, obs_lon):
        rx, ry, rz = sat_xyz
        ox, oy, oz = xyz_observer(obs_lat, obs_lon)
        dx, dy, dz = rx - ox, ry - oy, rz - oz
        d = math.sqrt(dx**2 + dy**2 + dz**2)
        if d == 0:
            return -90, 0
        # Up vector (local zenith)
        nx = math.cos(obs_lat) * math.cos(obs_lon)
        ny = math.cos(obs_lat) * math.sin(obs_lon)
        nz = math.sin(obs_lat)
        # East vector
        ex = -math.sin(obs_lon)
        ey = math.cos(obs_lon)
        ez = 0.0
        # North vector
        north_x = -math.sin(obs_lat) * math.cos(obs_lon)
        north_y = -math.sin(obs_lat) * math.sin(obs_lon)
        north_z = math.cos(obs_lat)
        dot_up = (dx * nx + dy * ny + dz * nz) / d
        el = math.degrees(math.asin(max(-1.0, min(1.0, dot_up))))
        e_comp = (dx * ex + dy * ey + dz * ez) / d
        n_comp = (dx * north_x + dy * north_y + dz * north_z) / d
        az = (math.degrees(math.atan2(e_comp, n_comp)) + 360) % 360
        return el, az

    # Load TLE
    try:
        from modules.iss_passes import fetch_iss_tle
        name, tle1, tle2 = fetch_iss_tle()
    except Exception:
        tle1 = tle2 = None

    if not tle1 or not tle2:
        return []

    try:
        from sgp4.api import Satrec, jday
    except ImportError:
        return []

    sat = Satrec.twoline2rv(tle1, tle2)
    obs_lat = math.radians(LAT_DEG)
    obs_lon = math.radians(LON_DEG)

    now = _dt.datetime.utcnow()
    passes = []
    in_pass = False
    pass_data = {}

    # Step 15s over next 48h
    for i in range(int(48 * 3600 / 15)):
        t = now + _dt.timedelta(seconds=i * 15)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
        err, r, v = sat.sgp4(jd, fr)
        if err != 0:
            continue
        el, az = el_az(r, obs_lat, obs_lon)
        if el >= 10.0:
            if not in_pass:
                in_pass = True
                pass_data = {
                    'start': t, 'start_az': az,
                    'max_el': el, 'max_t': t, 'max_az': az,
                    'prev_t': t, 'prev_el': el, 'prev_az': az
                }
            else:
                if el > pass_data['max_el']:
                    pass_data['max_el'] = el
                    pass_data['max_t'] = t
                    pass_data['max_az'] = az
                pass_data['prev_t'] = t
                pass_data['prev_el'] = el
                pass_data['prev_az'] = az
        else:
            if in_pass:
                in_pass = False
                end_t = pass_data['prev_t']
                dur_s = int((end_t - pass_data['start']).total_seconds())
                max_el = round(pass_data['max_el'], 1)
                # Visibility classification
                if max_el >= 45:
                    vis = 'excellent'
                elif max_el >= 20:
                    vis = 'good'
                else:
                    vis = 'fair'
                passes.append({
                    'datetime': pass_data['start'].strftime('%Y-%m-%dT%H:%M:%S'),
                    'datetime_end': end_t.strftime('%Y-%m-%dT%H:%M:%S'),
                    'duration_min': round(dur_s / 60, 1),
                    'max_elevation_deg': max_el,
                    'direction_start': _az_to_direction(pass_data['start_az']),
                    'direction_end': _az_to_direction(pass_data['prev_az']),
                    'az_start': round(pass_data['start_az'], 0),
                    'az_end': round(pass_data['prev_az'], 0),
                    'visibility': vis,
                    'timestamp_unix': int(pass_data['start'].replace(tzinfo=_dt.timezone.utc).timestamp()),
                })
                if len(passes) >= 5:
                    break

    return passes


def _compute_iss_passes_tlemcen():
    """Tlemcen (34.87°N, 1.32°E) — rétrocompat."""
    return _compute_iss_passes_for_observer(34.87, 1.32)


def _compute_iss_ground_track():
    """Trace au sol (lat, lon) sur ~90 min — SGP4 + position TEME (léger, pas de Skyfield)."""
    import datetime as _dt
    import math as _math

    def _teme_km_to_latlon(rx, ry, rz):
        """Approximation géodétique sphérique depuis vecteur position km (TEME)."""
        lon = _math.degrees(_math.atan2(ry, rx))
        hyp = _math.sqrt(rx * rx + ry * ry)
        lat = _math.degrees(_math.atan2(rz, hyp))
        return lat, lon

    try:
        from modules.iss_passes import fetch_iss_tle
        from sgp4.api import Satrec, jday
    except Exception:
        return {"track": []}
    try:
        _name, l1, l2 = fetch_iss_tle()
        if not l1 or not l2:
            return {"track": []}
        sat = Satrec.twoline2rv(l1, l2)
        track = []
        now = _dt.datetime.utcnow()
        for sec in range(0, 5400, 90):
            t = now + _dt.timedelta(seconds=sec)
            jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
            err, r, _v = sat.sgp4(jd, fr)
            if err != 0:
                continue
            lat, lon = _teme_km_to_latlon(r[0], r[1], r[2])
            if _math.isnan(lat) or _math.isnan(lon):
                continue
            track.append([round(lat, 4), round(lon, 4)])
        return {"track": track}
    except Exception as e:
        log.warning("iss ground-track compute: %s", e)
        return {"track": []}


@app.route("/api/iss/ground-track")
def api_iss_ground_track():
    """Orbite projetée au sol pour la carte ISS Tracker (cache 5 min)."""
    try:
        data = get_cached("iss_ground_track_v1", 300, _compute_iss_ground_track)
        return jsonify(data if isinstance(data, dict) else {"track": []})
    except Exception as e:
        log.warning("api/iss/ground-track: %s", e)
        return jsonify({"track": [], "error": str(e)})


@app.route("/api/iss/orbit")
def api_iss_orbit():
    """Trajectoire ISS future sur 90 minutes (pas 60s) via SGP4."""
    try:
        import math as _math
        import datetime as _dt
        from sgp4.api import Satrec, jday

        tle1, tle2 = _get_iss_tle_from_cache()
        if not tle1 or not tle2:
            return jsonify({"ok": False, "message": "TLE ISS indisponible", "points": [], "count": 0})

        sat = Satrec.twoline2rv(tle1, tle2)
        now = _dt.datetime.utcnow()
        points = []

        for sec in range(0, 90 * 60 + 1, 60):
            t = now + _dt.timedelta(seconds=sec)
            jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
            err, r, _v = sat.sgp4(jd, fr)
            if err != 0:
                continue

            rx, ry, rz = r[0], r[1], r[2]
            lon = _math.degrees(_math.atan2(ry, rx))
            hyp = _math.sqrt(rx * rx + ry * ry)
            lat = _math.degrees(_math.atan2(rz, hyp))
            alt = _math.sqrt(rx * rx + ry * ry + rz * rz) - 6371.0

            if not (_math.isfinite(lat) and _math.isfinite(lon) and _math.isfinite(alt)):
                continue

            points.append({
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "alt": round(alt, 2),
            })

        return jsonify({
            "ok": True,
            "points": points,
            "count": len(points),
        })
    except Exception as e:
        log.warning("api/iss/orbit: %s", e)
        return jsonify({
            "ok": False,
            "message": str(e),
            "points": [],
            "count": 0,
        })


@app.route("/api/iss/crew")
def api_iss_crew():
    """Équipage ISS — noms (open-notify / fallback), format UI iss_tracker."""
    try:
        from modules.orbit_engine import get_iss_crew
        raw = get_iss_crew()
        crew = []
        for c in raw or []:
            if isinstance(c, str):
                crew.append({"name": c, "photo_url": ""})
            elif isinstance(c, dict):
                crew.append({
                    "name": c.get("name") or "?",
                    "photo_url": c.get("photo_url") or "",
                })
        return jsonify({"ok": True, "crew": crew})
    except Exception as e:
        log.warning("api/iss/crew: %s", e)
        return jsonify({"ok": False, "crew": [], "error": str(e)})


@app.route("/api/iss/passes")
def api_iss_passes_tlemcen():
    """Prochains passages ISS sur Tlemcen — SGP4 local, cache 2h."""
    try:
        data = get_cached("iss_passes_rich", 7200, _compute_iss_passes_tlemcen)
        return jsonify(data)
    except Exception as e:
        log.warning("api/iss/passes: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/iss/passes/<float:lat>/<float:lon>")
def api_iss_passes_observer(lat, lon):
    """Prochains passages pour coordonnées (ville) — même moteur que Tlemcen."""
    if abs(lat) > 90 or abs(lon) > 180:
        return jsonify({"ok": False, "passes": [], "error": "coordonnées invalides"}), 400
    cache_key = "iss_passes_obs_{:.4f}_{:.4f}".format(lat, lon)

    def _fn():
        return _compute_iss_passes_for_observer(lat, lon)

    try:
        data = get_cached(cache_key, 7200, _fn)
        return jsonify({"ok": True, "passes": data if isinstance(data, list) else []})
    except Exception as e:
        log.warning("api/iss/passes/observer: %s", e)
        return jsonify({"ok": False, "passes": [], "error": str(e)}), 500


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


@app.route('/api/space-weather/alerts')
def api_space_weather_alerts():
    """Alertes NOAA SWPC dernières 24h — cache 30 min."""
    try:
        data = get_cached('swpc_alerts_24h', 1800, _fetch_swpc_alerts)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live/all')
def api_live_all():
    from modules.live_feeds import get_spacex_launches, get_space_news, get_mars_weather
    return jsonify({
        'spacex': get_cached('spacex', 3600, get_spacex_launches),
        'news': get_cached('space_news', 1800, get_space_news),
        'mars_weather': get_cached('mars_weather', 3600, get_mars_weather),
        'timestamp': __import__('datetime').datetime.utcnow().isoformat()
    })


@app.route('/api/iss-passes')
def api_iss_passes():
    import urllib.request
    try:
        lat = request.args.get('lat', '34.8')
        lon = request.args.get('lon', '1.3')
        key = os.environ.get('N2YO_API_KEY', 'DEMO')
        url = f'https://api.n2yo.com/rest/v1/satellite/visualpasses/25544/{lat}/{lon}/0/7/300/&apiKey={key}'
        def _fetch_n2yo():
            req = urllib.request.Request(url, headers={'User-Agent': 'AstroScan/1.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                return _safe_json_loads(r.read(), "n2yo_iss_passes")
        data = CB_N2YO.call(_fetch_n2yo, fallback=None)
        if data is None:
            return jsonify({'passes': [], 'count': 0, 'source': 'fallback (N2YO circuit ouvert)'})
        if not isinstance(data, dict):
            return jsonify({'passes': [], 'count': 0, 'error': 'invalid_response'})
        passes = []
        for p in data.get('passes', []):
            passes.append({
                'startUTC': p['startUTC'],
                'startAzCompass': p.get('startAzCompass', ''),
                'maxEl': p.get('maxEl', 0),
                'duration': p.get('duration', 0),
                'mag': p.get('mag', 0)
            })
        return jsonify({'passes': passes, 'count': len(passes)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/dsn')
def api_dsn():
    # DSN : fetch NASA + snapshot data_core/dsn/ + fallback — parsing XML inchangé dans core/dsn_engine_safe.parse_dsn_xml_to_payload
    try:
        from core import dsn_engine_safe as _dsn

        return jsonify(_dsn.get_dsn_safe(STATION))
    except Exception as e:
        log.warning("api/dsn: %s", e)
        try:
            from core import dsn_engine_safe as _dsn

            return jsonify(_dsn.build_dsn_fallback_payload())
        except Exception:
            return jsonify({
                'stations': [
                    {'friendlyName': 'Goldstone (USA)', 'name': 'GDS', 'dishes': []},
                    {'friendlyName': 'Madrid (Spain)', 'name': 'MDS', 'dishes': []},
                    {'friendlyName': 'Canberra (Australia)', 'name': 'CDS', 'dishes': []},
                ],
                'status': 'fallback',
            })








@app.route('/api/system-heal', methods=['POST'])
def api_system_heal():
    """Auto-healing contrôlé : refresh cache DSN / météo / SkyView (core/auto_heal_engine)."""
    try:
        from core import auto_heal_engine as _heal

        return jsonify(_heal.run_auto_heal(STATION))
    except Exception as e:
        log.warning("api/system-heal: %s", e)
        return jsonify({"actions": [], "count": 0, "error": str(e)}), 500




@app.route('/globe')
def globe():
    """Mission Control 3D plein écran — token Cesium depuis .env uniquement."""
    cesium_token = os.environ.get('CESIUM_ION_TOKEN', '')
    return render_template('globe.html', cesium_token=cesium_token)


@app.route('/api/survol')
def api_survol():
    try:
        import urllib.request
        iss_url = "https://api.wheretheiss.at/v1/satellites/25544"
        req = urllib.request.Request(iss_url)
        with urllib.request.urlopen(req, timeout=10) as r:
            iss_data = json.loads(r.read())
        lat = iss_data.get('latitude', 0)
        lon = iss_data.get('longitude', 0)

        geo_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=5"
        req2 = urllib.request.Request(geo_url, headers={'User-Agent': 'AstroScan-OrbitalChohra/2.0', 'Accept-Language': 'fr'})
        with urllib.request.urlopen(req2, timeout=10) as r2:
            geo_data = json.loads(r2.read())

        if isinstance(geo_data, dict) and geo_data.get('error'):
            zone = "🌊 Océan / Zone non cartographiée"
            pays = "Océan"
        else:
            addr = geo_data.get('address') or {}
            zone = geo_data.get('display_name', 'Inconnu')
            pays = addr.get('country', 'Inconnu')

        return jsonify({'lat': lat, 'lon': lon, 'zone': zone, 'pays': pays, 'statut': 'ok'})
    except Exception as e:
        log.warning("api/survol: %s", e)
        return jsonify({'statut': 'erreur', 'message': str(e)})


# ══════════════════════════════════════════════════════════════
# DIGITAL LAB — Image analysis pipeline (new module)
# ══════════════════════════════════════════════════════════════
LAB_UPLOADS = f'{STATION}/data/lab_uploads'
# Structure du laboratoire d'images
RAW_IMAGES = os.path.join(STATION, "data", "images_espace", "raw")
ANALYSED_IMAGES = os.path.join(STATION, "data", "analysed")
MAX_LAB_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB guardrail
METADATA_DB = os.path.join(STATION, "data", "metadata")
LAB_LOGS_DIR = os.path.join(STATION, "data", "images_espace", "logs")
os.makedirs(RAW_IMAGES, exist_ok=True)
os.makedirs(ANALYSED_IMAGES, exist_ok=True)
os.makedirs(METADATA_DB, exist_ok=True)
os.makedirs(LAB_LOGS_DIR, exist_ok=True)
# Dossier SkyView — captures alimentent le lab via _sync_skyview_to_lab()
SKYVIEW_DIR = os.path.join(STATION, "data", "skyview")
os.makedirs(SKYVIEW_DIR, exist_ok=True)
# Espace d'images utilisé par le Lab (compatibilité avec code existant)
SPACE_IMAGE_DB = RAW_IMAGES
_lab_last_report = {}


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


@app.route('/lab')
def digital_lab():
    return render_template('lab.html')


@app.route("/lab/upload", methods=["POST"])
def lab_upload():
    if "image" not in request.files:
        return jsonify({"error": "no image"}), 400
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "no image"}), 400
    allowed = (".jpg", ".jpeg", ".png", ".fits", ".fit")
    filename = secure_filename(file.filename)
    req_len = request.content_length or 0
    if req_len and req_len > MAX_LAB_IMAGE_BYTES:
        return jsonify({"error": "image too large"}), 413
    if not filename.lower().endswith(allowed):
        return jsonify({"error": "invalid format"}), 400
    path = os.path.join(SPACE_IMAGE_DB, filename)
    if os.path.exists(path):
        filename = str(int(time.time())) + "_" + filename
        path = os.path.join(SPACE_IMAGE_DB, filename)
    try:
        file.save(path)
        # Métadonnées scientifiques étendues
        meta = {
            "source": "UPLOAD",
            "filename": filename,
            "date": datetime.utcnow().isoformat() + "Z",
            "telescope": "unknown",
            "object_name": "unknown",
            "instrument": "unknown",
        }
        meta_path = os.path.join(METADATA_DB, filename + ".json")
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            log.warning("lab/upload metadata: %s", e)
        return jsonify({"status": "saved", "file": filename, "path": path})
    except Exception as e:
        log.warning("lab/upload: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/lab/images")
def lab_images():
    try:
        files = [f for f in os.listdir(SPACE_IMAGE_DB) if os.path.isfile(os.path.join(SPACE_IMAGE_DB, f)) and not f.endswith(".json")]
        return jsonify({"images": files})
    except Exception as e:
        log.warning("lab/images: %s", e)
        return jsonify({"images": []})


@app.route("/api/lab/images")
def api_lab_images():
    """Liste les images brutes disponibles pour le Digital Lab (PNG/JPG)."""
    try:
        exts = (".png", ".jpg", ".jpeg")
        entries = []
        for name in os.listdir(RAW_IMAGES):
            if not name.lower().endswith(exts):
                continue
            path = os.path.join(RAW_IMAGES, name)
            if not os.path.isfile(path):
                continue
            entries.append({"file": name, "mtime": os.path.getmtime(path)})
        entries.sort(key=lambda x: x["mtime"], reverse=True)
        images = [{"file": e["file"], "url": f"/lab/raw/{e['file']}"} for e in entries]
        return jsonify({"images": images})
    except Exception as e:
        log.warning("api/lab/images: %s", e)
        return jsonify({"images": []})


@app.route("/lab/raw/<path:filename>")
def lab_raw_file(filename):
    """Servez les fichiers bruts du laboratoire (images) depuis RAW_IMAGES."""
    return send_from_directory(RAW_IMAGES, filename, as_attachment=False)


@app.route("/api/lab/metadata/<path:filename>")
def api_lab_metadata(filename):
    """Return normalized metadata JSON for a lab image file, if present."""
    try:
        safe = secure_filename(os.path.basename(filename)) or filename
        meta_path = os.path.join(METADATA_DB, safe + ".json")
        if not os.path.isfile(meta_path):
            return jsonify({})
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        log.warning("api/lab/metadata: %s", e)
        return jsonify({})


@app.route("/lab/analyze", methods=["POST"])
def lab_analyze():
    if "image" not in request.files:
        return jsonify({"error": "no image", "stars_detected": 0, "objects_detected": 0, "brightness_mean": 0, "report": {}}), 400
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "no image", "stars_detected": 0, "objects_detected": 0, "brightness_mean": 0, "report": {}}), 400
    try:
        from modules.digital_lab import run_pipeline
        filename = secure_filename(file.filename) or "analyzed.png"
        data_bytes = file.read()
        try:
            os.makedirs(ANALYSED_IMAGES, exist_ok=True)
            analysed_path = os.path.join(ANALYSED_IMAGES, filename)
            with open(analysed_path, "wb") as out_f:
                out_f.write(data_bytes)
        except Exception as e:
            log.warning("lab/analyze save analysed: %s", e)
        result = run_pipeline(data_bytes)
        stars_detected = len(result.get("stars") or [])
        objects_detected = len(result.get("objects") or [])
        brightness = result.get("brightness") or {}
        brightness_mean = float(brightness.get("global_mean", 0.0))
        report = result.get("report") or {}
        def _to_native(obj):
            if hasattr(obj, "item"):
                return obj.item()
            if isinstance(obj, dict):
                return {k: _to_native(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_to_native(x) for x in obj]
            return obj
        return jsonify({
            "stars_detected": stars_detected,
            "objects_detected": objects_detected,
            "brightness_mean": _to_native(brightness_mean),
            "report": _to_native(report),
        })
    except Exception as e:
        log.warning("lab/analyze: %s", e)
        return jsonify({
            "error": str(e),
            "stars_detected": 0,
            "objects_detected": 0,
            "brightness_mean": 0,
            "report": {},
        }), 500


@app.route("/lab/dashboard")
def lab_dashboard():
    """Dashboard: number_of_images, latest_images, sources (from metadata)."""
    try:
        files = [f for f in os.listdir(SPACE_IMAGE_DB)
                 if os.path.isfile(os.path.join(SPACE_IMAGE_DB, f))
                 and not f.endswith(".json")]
        latest = sorted(files, key=lambda f: os.path.getmtime(os.path.join(SPACE_IMAGE_DB, f)), reverse=True)[:10]
        sources = set()
        for f in files:
            meta_path = os.path.join(METADATA_DB, f + ".json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as fp:
                        m = json.load(fp)
                        sources.add(m.get("source", "unknown"))
                except Exception:
                    pass
        return jsonify({
            "number_of_images": len(files),
            "latest_images": latest,
            "sources": list(sources) if sources else ["NASA APOD", "HUBBLE", "JWST", "ESA", "UPLOAD"],
        })
    except Exception as e:
        log.warning("lab/dashboard: %s", e)
        return jsonify({"number_of_images": 0, "latest_images": [], "sources": []})


@app.route("/api/lab/run_analysis", methods=["POST"])
def api_lab_run_analysis():
    """Analyze the newest image in RAW_IMAGES using the Digital Lab pipeline."""
    from modules.digital_lab import run_pipeline

    exts = (".png", ".jpg", ".jpeg", ".fits", ".fit")
    candidates = []

    for name in os.listdir(RAW_IMAGES):
        if name.lower().endswith(exts):
            path = os.path.join(RAW_IMAGES, name)
            if os.path.isfile(path):
                candidates.append((os.path.getmtime(path), name))

    if not candidates:
        return jsonify({"error": "no images available"}), 400

    candidates.sort(reverse=True)

    filename = candidates[0][1]
    path = os.path.join(RAW_IMAGES, filename)

    result = run_pipeline(path)

    return jsonify({
        "status": "ok",
        "filename": filename,
        "report": result
    })


@app.route("/api/lab/skyview/sync")
def force_skyview_sync():
    """Force une synchronisation immédiate SkyView → Lab."""
    _sync_skyview_to_lab()
    return jsonify({"status": "skyview_sync_ok"})


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


def _sync_skyview_to_lab():
    """Copie les images du dossier SkyView vers RAW_IMAGES et crée les métadonnées lab."""
    import shutil
    try:
        HEALTH_STATE["collector_status"]["skyview_sync"] = "running"
    except Exception:
        pass
    for file in os.listdir(SKYVIEW_DIR):
        src = os.path.join(SKYVIEW_DIR, file)
        dst = os.path.join(RAW_IMAGES, file)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
                meta = {
                    "source": "SKYVIEW",
                    "telescope": "SkyView Observatory",
                    "filename": file,
                    "date": datetime.utcnow().isoformat() + "Z",
                }
                meta_path = os.path.join(METADATA_DB, file + ".json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception as e:
                log.warning("SkyView sync error %s", e)
                _health_set_error("skyview_sync", e, "warn")
    try:
        HEALTH_STATE["collector_status"]["skyview_sync"] = "ok"
        HEALTH_STATE["skyview_status"] = "ok"
    except Exception:
        pass


def _start_skyview_sync():
    """Boucle de sync SkyView → Lab toutes les 60 secondes."""
    import threading
    def loop():
        while True:
            _sync_skyview_to_lab()
            time.sleep(60)
    t = threading.Thread(target=loop, daemon=True)
    t.start()


LOCK_FILE = '/tmp/aegis_collector.lock'
LAST_RUN_FILE = '/tmp/aegis_collector.lastrun'
COOLDOWN_SECONDS = 60


def _aegis_collector_acquire_lock():
    try:
        lock_file = open(LOCK_FILE, 'a+')
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except Exception:
        return None


def _aegis_collector_release_lock(lock_file):
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
    except Exception:
        pass


def _aegis_collector_can_run():
    try:
        if not os.path.exists(LAST_RUN_FILE):
            return True
        with open(LAST_RUN_FILE, 'r') as f:
            last = float(f.read().strip())
        return (time.time() - last) > COOLDOWN_SECONDS
    except Exception:
        return True


def _aegis_collector_mark_run():
    global COLLECTOR_LAST_RUN
    try:
        with open(LAST_RUN_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception:
        pass
    COLLECTOR_LAST_RUN = time.time()


def run_collector_safe(run_func):
    lock = _aegis_collector_acquire_lock()
    if not lock:
        log.info('[AEGIS] Collector skipped (already running)')
        return
    try:
        if not _aegis_collector_can_run():
            log.info('[AEGIS] Collector skipped (cooldown active)')
            return
        log.info('[AEGIS] Collector START (secured)')
        run_func()
        _aegis_collector_mark_run()
        log.info('[AEGIS] Collector END (secured)')
    except Exception as e:
        log.error('[AEGIS] Collector ERROR: %s', e)
    finally:
        _aegis_collector_release_lock(lock)


def _run_lab_image_collector_once():
    try:
        HEALTH_STATE["collector_status"]["image_collector"] = "running"
    except Exception:
        pass
    log.info("[LAB COLLECTOR] Starting telescope download")
    try:
        from modules.space_sources import run_telescope_collector
        run_telescope_collector(RAW_IMAGES, METADATA_DB)
    except Exception as e:
        log.warning("run_telescope_collector: %s", e)
        _health_set_error("lab_image_collector", e, "warn")
    log.info("[LAB COLLECTOR] Syncing SkyView to Lab")
    _sync_skyview_to_lab()
    log.info("[LAB COLLECTOR] NASA APOD download")
    _download_nasa_apod()
    _download_hubble_images()
    _download_jwst_images()
    _download_esa_images()
    log.info("[LAB COLLECTOR] Completed cycle")
    try:
        HEALTH_STATE["collector_status"]["image_collector"] = "ok"
        HEALTH_STATE["last_sync"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            HEALTH_STATE["image_count"] = len(os.listdir(RAW_IMAGES))
        except Exception:
            HEALTH_STATE["image_count"] = HEALTH_STATE.get("image_count")
    except Exception:
        pass
    import threading
    t = threading.Timer(
        86400.0,
        run_collector_safe,
        args=(_run_lab_image_collector_once,),
    )
    t.daemon = True
    t.start()


def _start_lab_image_collector():
    import threading
    def _run():
        time.sleep(60)
        run_collector_safe(_run_lab_image_collector_once)
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def translate_worker():
    """
    Daemon worker:
    - every 10 minutes, translate/summarize up to 5 observations with empty rapport_fr
    - never runs in Flask request context
    """
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT id, analyse_gemini FROM observations "
                "WHERE COALESCE(TRIM(rapport_fr), '') = '' "
                "AND COALESCE(TRIM(analyse_gemini), '') <> '' "
                "LIMIT 5"
            ).fetchall()

            for row in rows:
                obs_id = row["id"]
                src = (row["analyse_gemini"] or "").strip()
                if not src:
                    continue
                prompt = (
                    "Résume en 2 phrases en français pour l'observatoire "
                    "ORBITAL-CHOHRA à Tlemcen : " + row["analyse_gemini"][:500]
                )
                reply, err = _call_gemini(prompt)
                if reply and len(str(reply).strip()) > 0:
                    try:
                        cur.execute(
                            "UPDATE observations SET rapport_fr=? WHERE id=?",
                            (str(reply).strip(), obs_id),
                        )
                        conn.commit()
                    except Exception as e_upd:
                        log.warning("translate_worker update id=%s: %s", obs_id, e_upd)
            conn.close()
        except Exception as e:
            log.warning("translate_worker: %s", e)
        try:
            time.sleep(600)
        except Exception:
            time.sleep(60)


_start_lab_image_collector()
_start_skyview_sync()
try:
    threading.Thread(target=translate_worker, daemon=True).start()
except Exception as e:
    log.warning("translate_worker start: %s", e)


# ══════════════════════════════════════════════════════════════
# Catalogue TLE complet (Celestrak) — data/tle/, /api/tle/full
# ══════════════════════════════════════════════════════════════
TLE_DIR = os.path.join(STATION, "data", "tle")
os.makedirs(TLE_DIR, exist_ok=True)
TLE_ACTIVE_PATH = os.path.join(TLE_DIR, "active.tle")

TLE_MAX_SATELLITES = 200


def download_tle_now():
    """Download Celestrak active TLE at startup so /api/satellites/tle has real data."""
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
            import urllib.request
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
    import urllib.request

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

        # Update in-memory cache/status
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
    import urllib.request
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


def _parse_tle_file(path, limit=None):
    """Parse un fichier TLE (blocs de 3 lignes: name, line1, line2). Retourne [ { name, line1, line2 }, ... ], max `limit` entries."""
    out = []
    if not path or not os.path.isfile(path):
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip("\r\n") for line in f.readlines()]
        i = 0
        while i + 2 < len(lines) and (limit is None or len(out) < limit):
            name = (lines[i] or "").strip()
            line1 = (lines[i + 1] or "").strip()
            line2 = (lines[i + 2] or "").strip()
            if line1.startswith("1 ") and line2.startswith("2 "):
                out.append({"name": name or "Unknown", "line1": line1, "line2": line2})
            i += 3
    except Exception as e:
        log.warning("parse_tle_file: %s", e)
    return out


@app.route("/api/satellites/tle")
def api_satellites_tle():
    """
    Serves real Celestrak active TLE from data/tle/active.tle. Fallback only if file missing or empty.
    """
    try:
        satellites = _parse_tle_file(TLE_ACTIVE_PATH, limit=TLE_MAX_SATELLITES)
        if not satellites:
            log.info("api/satellites/tle: cache empty or missing, using fallback TLE")
            satellites = [
                {"name": s["name"], "line1": s["tle1"], "line2": s["tle2"]}
                for s in _TLE_FOR_PASSES
            ]
        out = [
            {"name": s.get("name", "Unknown"), "tle1": s.get("line1", ""), "tle2": s.get("line2", "")}
            for s in satellites[:TLE_MAX_SATELLITES]
        ]
        log.info("TLE satellites served: %s", len(out))
        if os.path.isfile(TLE_ACTIVE_PATH):
            log.info("TLE FILE SIZE: %s", os.path.getsize(TLE_ACTIVE_PATH))
        return jsonify({
            "source": "celestrak",
            "group": "active",
            "format": "tle",
            "satellites": out,
        })
    except Exception as e:
        log.warning("api/satellites/tle: %s", e)
        return jsonify({
            "source": "celestrak",
            "group": "active",
            "format": "tle",
            "satellites": [],
        })


@app.route("/api/satellites/tle/debug")
def debug_tle():
    exists = os.path.exists(TLE_ACTIVE_PATH)
    size = os.path.getsize(TLE_ACTIVE_PATH) if exists else 0
    sats = _parse_tle_file(TLE_ACTIVE_PATH, limit=10) if exists else []
    return jsonify({
        "file_exists": exists,
        "file_size": size,
        "satellite_count": len(sats),
        "sample": sats[:2],
    })


@app.route("/api/tle/full")
def api_tle_full():
    """Catalogue TLE complet (parsed depuis data/tle/active.tle). orbital_map.html peut charger cette API."""
    try:
        satellites = _parse_tle_file(TLE_ACTIVE_PATH)
        return jsonify({"satellites": satellites})
    except Exception as e:
        log.warning("api/tle/full: %s", e)
        return jsonify({"satellites": []})


def _run_tle_download_once():
    try:
        refresh_tle_from_amsat()
    except Exception:
        try:
            print("TLE skipped — offline mode")
        except Exception:
            pass
    import threading
    t = threading.Timer(6 * 3600.0, _run_tle_download_once)
    t.daemon = True
    t.start()


def _start_tle_collector():
    import threading
    def _run():
        time.sleep(60)
        _run_tle_download_once()
    t = threading.Thread(target=_run, daemon=True)
    t.start()


_start_tle_collector()
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


# Données TLE pour prédiction de passages (lecture seule, ne pas modifier api/tle/catalog)
_TLE_FOR_PASSES = [
    {"name": "Hubble", "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993", "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"},
    {"name": "NOAA 19", "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996", "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"},
]


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


@app.route("/api/satellite/passes")
def api_satellite_passes():
    """Prédiction des prochains passages (élévation > 10°) pour un observateur lat/lon. Utilisable par le radar."""
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon required", "passes": []}), 400
    passes_out = []
    try:
        from sgp4.api import Satrec, jday
        import math
        # Observateur ECEF (km) puis conversion TEME pour un jd donné
        rad = math.radians
        a, b = 6378.137, 6356.752
        coslat = math.cos(rad(lat))
        sinlat = math.sin(rad(lat))
        n = a * a / math.sqrt(a * a * coslat * coslat + b * b * sinlat * sinlat)
        x_ecef = (n + 0) * coslat * math.cos(rad(lon))
        y_ecef = (n + 0) * coslat * math.sin(rad(lon))
        z_ecef = (n * (b * b) / (a * a) + 0) * sinlat
        obs_ecef = (x_ecef, y_ecef, z_ecef)
        obs_norm = math.sqrt(x_ecef * x_ecef + y_ecef * y_ecef + z_ecef * z_ecef)

        def obs_teme_at(jd, fr):
            t = (jd - 2451545.0) + fr
            gmst_deg = (280.46061837 + 360.98564736629 * t) % 360
            gmst = math.radians(gmst_deg)
            c, s = math.cos(gmst), math.sin(gmst)
            return (c * obs_ecef[0] - s * obs_ecef[1], s * obs_ecef[0] + c * obs_ecef[1], obs_ecef[2])

        from datetime import timedelta
        now = datetime.utcnow()
        # Fenêtre 24 h, pas 2 min
        for sat in _TLE_FOR_PASSES:
            rec = Satrec.twoline2rv(sat["tle1"], sat["tle2"])
            next_pass_dt = None
            max_elev = 0.0
            for minute in range(0, 24 * 60, 2):
                t = now + timedelta(minutes=minute)
                jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
                obs_teme = obs_teme_at(jd, fr)
                e, r, v = rec.sgp4(jd, fr)
                if e != 0:
                    continue
                elev = _elevation_above_observer(lat, lon, jd, fr, obs_teme, obs_norm, (r[0], r[1], r[2]))
                if elev > 10:
                    if next_pass_dt is None:
                        next_pass_dt = t
                    max_elev = max(max_elev, elev)
                elif next_pass_dt is not None:
                    break
            if next_pass_dt is not None:
                passes_out.append({
                    "name": sat["name"],
                    "elevation": round(max_elev, 1),
                    "next_pass": next_pass_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
    except ImportError:
        log.warning("api/satellite/passes: sgp4 not installed, returning empty passes")
        return jsonify({"passes": [], "message": "Install sgp4 for pass prediction"})
    except Exception as e:
        log.warning("api/satellite/passes: %s", e)
        return jsonify({"passes": [], "error": str(e)})
    return jsonify({"passes": passes_out})


@app.route('/research')
def research():
    """Scientific research dashboard — Digital Lab, anomaly detector, solar, NEO, discoveries."""
    return render_template('research.html')


@app.route('/space')
def space():
    return render_template('space.html')


@app.route('/space-intelligence')
def space_intelligence():
    return redirect('/space')


@app.route("/module/<name>")
def module(name):
    # Compatibilité route legacy : certains modules nécessitent un contexte (ex: /galerie).
    # Rediriger vers la route officielle évite les 500 sans toucher au rendu public.
    module_routes = {
        "galerie": "/galerie",
        "observatoire": "/observatoire",
        "portail": "/portail",
        "dashboard": "/dashboard",
        "ce_soir": "/ce_soir",
    }
    target = module_routes.get((name or "").strip().lower())
    if target:
        return redirect(target)

    template = f"{name}.html"
    template_path = f"/root/astro_scan/templates/{template}"
    if os.path.exists(template_path):
        try:
            return render_template(template)
        except Exception as e:
            log.warning("module/%s render failed: %s", name, e)
            return redirect("/portail")

    return f"""
<html>
<head>
<title>Orbital-Chohra</title>
<style>
body {{
    background:#020b14;
    color:#00eaff;
    font-family:monospace;
    text-align:center;
    padding-top:120px;
}}
a {{
    color:#00ffaa;
    text-decoration:none;
    font-size:18px;
}}
</style>
</head>

<body>
    <h1>MODULE {name.upper()}</h1>
    <p>Module actif – contenu en cours de chargement</p>
    <br>
    <a href="/portail">⬅ Retour portail</a>
</body>
</html>
"""


@app.route('/api/lab/upload', methods=['POST'])
def api_lab_upload():
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        ip = ip.split(",")[0].strip()
        allowed, retry = _api_rate_limit_allow(f"lab_upload:{ip}", limit=30, window_sec=60)
        if not allowed:
            return jsonify({
                'error': f'Trop de televersements. Reessayez dans {retry}s.',
                'retry_after': retry
            }), 429
        os.makedirs(LAB_UPLOADS, exist_ok=True)
        f = request.files.get('image')
        if not f or not f.filename:
            return jsonify({'error': 'No image file provided'}), 400
        req_len = request.content_length or 0
        if req_len and req_len > MAX_LAB_IMAGE_BYTES:
            return jsonify({'error': 'Image trop volumineuse (max 25 MB)'}), 413
        import uuid
        ext = os.path.splitext(f.filename)[1] or '.png'
        name = str(uuid.uuid4()) + ext
        path = os.path.join(LAB_UPLOADS, name)
        f.save(path)
        return jsonify({'id': name, 'path': name, 'uploaded': True})
    except Exception as e:
        log.warning("api/lab/upload: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/lab/analyze', methods=['POST'])
def api_lab_analyze():
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        ip = ip.split(",")[0].strip()
        allowed, retry = _api_rate_limit_allow(f"lab_analyze:{ip}", limit=20, window_sec=60)
        if not allowed:
            return jsonify({
                'error': f'Trop d analyses. Reessayez dans {retry}s.',
                'retry_after': retry
            }), 429
        from modules.digital_lab import run_pipeline
        source = None
        payload = request.get_json(silent=True) or {}
        if request.files.get('image'):
            f = request.files['image']
            req_len = request.content_length or 0
            if req_len and req_len > MAX_LAB_IMAGE_BYTES:
                return jsonify({'error': 'Image trop volumineuse pour analyse (max 25 MB)', 'report': {}}), 413
            source = f.read()
        elif payload.get('upload_id'):
            path = os.path.join(LAB_UPLOADS, payload['upload_id'])
            if os.path.isfile(path):
                source = path
        elif payload.get('raw_file'):
            raw_name = secure_filename(os.path.basename(str(payload.get('raw_file'))))
            raw_path = os.path.join(RAW_IMAGES, raw_name)
            if os.path.isfile(raw_path):
                source = raw_path
        if source is None:
            return jsonify({'error': 'Provide image file, upload_id or raw_file in JSON'}), 400
        result = run_pipeline(source)
        def _to_native(obj):
            if hasattr(obj, 'item'):
                return obj.item()
            if isinstance(obj, dict):
                return {k: _to_native(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_to_native(x) for x in obj]
            return obj
        result = _to_native(result)
        _lab_last_report['report'] = result.get('report', {})
        _lab_last_report['full'] = {k: v for k, v in result.items() if k != 'report' and not (isinstance(v, (list, dict)) and len(str(v)) > 2000)}
        return jsonify(result)
    except Exception as e:
        log.warning("api/lab/analyze: %s", e)
        return jsonify({'error': str(e), 'report': {}}), 500


@app.route('/api/lab/report', methods=['GET'])
def api_lab_report():
    try:
        report = _lab_last_report.get('report', {})
        if not report:
            return jsonify({'report': {}, 'message': 'Run /api/lab/analyze first'})
        return jsonify({'report': report})
    except Exception as e:
        return jsonify({'error': str(e), 'report': {}}), 500


# ══════════════════════════════════════════════════════════════
# SPACE ANALYSIS ENGINE — Advanced scientific module (new)
# Consumes digital_lab pipeline results; does not modify digital_lab
# ══════════════════════════════════════════════════════════════
@app.route('/api/analysis/run', methods=['POST'])
def api_analysis_run():
    try:
        from modules.space_analysis_engine import run_analysis
        data = request.get_json(silent=True) or {}
        pipeline_result = data.get('pipeline_result')
        source = data.get('source', 'upload')
        if not pipeline_result:
            return jsonify({'error': 'Provide pipeline_result (output of digital_lab run_pipeline)'}), 400
        result = run_analysis(pipeline_result, source=source)
        return jsonify(result)
    except Exception as e:
        log.warning("api/analysis/run: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/compare', methods=['POST'])
def api_analysis_compare():
    try:
        from modules.space_analysis_engine import compare_results_from_sources
        data = request.get_json(silent=True) or {}
        result_a = data.get('result_a')
        result_b = data.get('result_b')
        source_a = data.get('source_a', 'source_a')
        source_b = data.get('source_b', 'source_b')
        if not result_a or not result_b:
            return jsonify({'error': 'Provide result_a and result_b (pipeline results)'}), 400
        out = compare_results_from_sources(result_a, result_b, source_a=source_a, source_b=source_b)
        return jsonify(out)
    except Exception as e:
        log.warning("api/analysis/compare: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/discoveries', methods=['GET'])
def api_analysis_discoveries():
    try:
        from modules.space_analysis_engine import get_discoveries
        limit = request.args.get('limit', 100, type=int)
        discoveries = get_discoveries(limit=min(limit, 500))
        return jsonify({'discoveries': discoveries, 'count': len(discoveries)})
    except Exception as e:
        log.warning("api/analysis/discoveries: %s", e)
        return jsonify({'error': str(e), 'discoveries': []}), 500


# ══════════════════════════════════════════════════════════════
# RESEARCH CENTER — Aggregated scientific data (new)
# Uses modules.research_center; does not modify existing modules
# ══════════════════════════════════════════════════════════════
@app.route('/research-center')
def research_center_page():
    """Research Center dashboard: Space Weather, NEO, Solar Activity, Reports."""
    return render_template('research_center.html')


@app.route('/api/research/summary', methods=['GET'])
def api_research_summary():
    try:
        from modules.research_center import get_research_summary
        data = get_research_summary()
        return jsonify(data)
    except Exception as e:
        log.warning("api/research/summary: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/research/events', methods=['GET'])
def api_research_events():
    try:
        from modules.research_center import get_research_events
        limit = request.args.get('limit', 50, type=int)
        events = get_research_events(limit=min(limit, 200))
        return jsonify({'events': events})
    except Exception as e:
        log.warning("api/research/events: %s", e)
        return jsonify({'error': str(e), 'events': []}), 500


@app.route('/api/research/logs', methods=['GET'])
def api_research_logs():
    try:
        from modules.research_center import list_logs
        limit = request.args.get('limit', 50, type=int)
        logs = list_logs(limit=min(limit, 200))
        return jsonify({'logs': logs})
    except Exception as e:
        log.warning("api/research/logs: %s", e)
        return jsonify({'error': str(e), 'logs': []}), 500


# ══════════════════════════════════════════════════════════════
# SCIENCE ARCHIVE — Automatic archive for scientific outputs (new)
# Receives results from Digital Lab / Space Analysis via API; does not modify existing modules
# ══════════════════════════════════════════════════════════════
@app.route('/api/archive/reports', methods=['GET', 'POST'])
def api_archive_reports():
    try:
        from modules.science_archive_engine import save_report, list_reports, get_archive_index
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            report_data = data.get('report', data)
            source = data.get('source', 'digital_lab')
            result = save_report(report_data, source=source)
            return jsonify({'ok': True, 'saved': result})
        limit = request.args.get('limit', 50, type=int)
        reports = list_reports(limit=min(limit, 200))
        index = get_archive_index()
        return jsonify({'reports': reports, 'index': index})
    except Exception as e:
        log.warning("api/archive/reports: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/archive/objects', methods=['GET', 'POST'])
def api_archive_objects():
    try:
        from modules.science_archive_engine import save_objects, list_objects, get_archive_index
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            objects = data.get('objects', data.get('objects_list', []))
            if isinstance(objects, dict):
                objects = [objects]
            source = data.get('source', 'archive_api')
            result = save_objects(objects, source=source)
            return jsonify({'ok': True, 'saved': result})
        limit = request.args.get('limit', 100, type=int)
        objects = list_objects(limit=min(limit, 500))
        index = get_archive_index()
        return jsonify({'objects': objects, 'index': index})
    except Exception as e:
        log.warning("api/archive/objects: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/archive/discoveries', methods=['GET', 'POST'])
def api_archive_discoveries():
    try:
        from modules.science_archive_engine import save_discovery, list_discoveries, get_archive_index
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            source = data.get('source', 'archive_api')
            entry = {k: v for k, v in data.items() if k != 'source'}
            result = save_discovery(entry, source=source)
            return jsonify({'ok': True, 'saved': result})
        limit = request.args.get('limit', 50, type=int)
        discoveries = list_discoveries(limit=min(limit, 200))
        index = get_archive_index()
        return jsonify({'discoveries': discoveries, 'index': index})
    except Exception as e:
        log.warning("api/archive/discoveries: %s", e)
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# Carte orbitale mondiale — positions satellites live
# ══════════════════════════════════════════════════════════════

# MIGRATED TO iss_bp 2026-05-02 (B3b) — see app/blueprints/iss/routes.py
# @app.route('/orbital-map')
# def orbital_map_page():
#     return render_template('orbital_map.html', cesium_token=CESIUM_TOKEN)


@app.route('/demo')
def astroscan_demo_page():
    """Page produit : liens MASTER / VIEWER et test WS pour démo client."""
    return render_template('demo.html')


@app.route('/api/orbits/live')
def api_orbits_live():
    """Positions satellites pour la carte orbitale : ISS, NOAA (placeholder si dispo). Cache 30 s."""
    cache_cleanup()
    cached = cache_get("orbits_live", 30)
    if cached is not None:
        return jsonify(cached)
    satellites = []
    iss = get_cached('iss_live', 5, _fetch_iss_live)
    if iss:
        lat = iss.get('latitude') if 'latitude' in iss else iss.get('lat', 0)
        lon = iss.get('longitude') if 'longitude' in iss else iss.get('lon', 0)
        satellites.append({
            'id': 'iss',
            'name': 'ISS',
            'lat': float(lat),
            'lon': float(lon),
            'type': 'iss',
            'alt': iss.get('alt', iss.get('altitude', 408)),
        })
    for name, lat, lon in [('NOAA-19', 45.0, -122.0), ('NOAA-18', -30.0, 10.0), ('NOAA-15', 20.0, 80.0)]:
        satellites.append({'id': name.lower().replace('-', '_'), 'name': name, 'lat': lat, 'lon': lon, 'type': 'noaa'})
    payload = {'satellites': satellites, 'timestamp': int(time.time())}
    cache_set("orbits_live", payload)
    return jsonify(payload)


# ══════════════════════════════════════════════════════════════
# Météo spatiale
# ══════════════════════════════════════════════════════════════

@app.route('/api/space-weather')
def api_space_weather():
    """Données météo spatiale depuis static/space_weather.json. Cache 60 s."""
    cache_cleanup()
    cached = cache_get("space_weather", 60)
    if cached is not None:
        return jsonify(cached)
    try:
        path = f"{STATION}/static/space_weather.json"
        if not os.path.exists(path):
            data = {'statut_magnetosphere': 'Indisponible', 'kp_index': None}
        else:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {'statut_magnetosphere': 'Indisponible'}
        cache_set("space_weather", data)
        return jsonify(data)
    except Exception as e:
        log.warning("api/space-weather: %s", e)
        return jsonify({'statut_magnetosphere': 'Indisponible'})


@app.route('/space-weather')
def space_weather_page():
    return render_template('space_weather.html')


# ══════════════════════════════════════════════════════════════
# Analyse scientifique d'images
# ══════════════════════════════════════════════════════════════

@app.route('/api/science/analyze-image', methods=['POST'])
def api_science_analyze_image():
    """Analyse d'image spatiale via image_science_engine."""
    try:
        from modules.image_science_engine import analyze_space_image
        f = request.files.get('image')
        if f and f.filename:
            import uuid
            ext = os.path.splitext(f.filename)[1] or '.png'
            name = str(uuid.uuid4()) + ext
            path = os.path.join(LAB_UPLOADS, name)
            os.makedirs(LAB_UPLOADS, exist_ok=True)
            f.save(path)
            result = analyze_space_image(path)
            return jsonify(result)
        path = request.form.get('path') or (request.get_json(silent=True) or {}).get('path')
        if path:
            full = path if os.path.isabs(path) else os.path.join(STATION, path)
            result = analyze_space_image(full)
            return jsonify(result)
        return jsonify({'error': 'Aucune image fournie (fichier ou path)'}), 400
    except Exception as e:
        log.warning("api/science/analyze-image: %s", e)
        return jsonify({'error': str(e), 'stars': 0, 'galaxies': 0, 'nebula': False, 'anomalies': []}), 500


# ══════════════════════════════════════════════════════════════
# Mission Control — vue consolidée
# ══════════════════════════════════════════════════════════════

@app.route('/api/missions/overview')
def api_missions_overview():
    """Regroupe ISS, Voyager, SDR pour le centre de contrôle."""
    iss = get_cached('iss_live', 5, _fetch_iss_live) or {'ok': False, 'lat': 0, 'lon': 0, 'alt': 408}
    voyager = {}
    try:
        vpath = f"{STATION}/static/voyager_live.json"
        if os.path.exists(vpath):
            with open(vpath, 'r', encoding='utf-8') as f:
                voyager = json.load(f)
    except Exception:
        voyager = {'statut': 'Indisponible'}
    sdr = {}
    if Path(SDR_F).exists():
        try:
            sdr = json.load(open(SDR_F))
        except Exception:
            sdr = {'status': 'standby'}
    else:
        sdr = {'status': 'standby', 'ok': True}
    alerts = []
    try:
        apath = f"{STATION}/static/space_weather.json"
        if os.path.exists(apath):
            with open(apath, 'r', encoding='utf-8') as f:
                sw = json.load(f)
            if isinstance(sw, dict) and (sw.get('kp_index') or 0) >= 5:
                alerts.append('Activité géomagnétique élevée')
    except Exception:
        pass
    return jsonify({
        'iss': iss,
        'voyager': voyager,
        'sdr': sdr,
        'alerts': alerts,
        'timestamp': int(time.time()),
    })


# ══════════════════════════════════════════════════════════════
# Intelligence spatiale
# ══════════════════════════════════════════════════════════════

@app.route('/api/space/intelligence', methods=['GET', 'POST'])
def api_space_intelligence():
    """Analyse spatiale : alertes, événements, niveau de risque."""
    try:
        from modules.space_intelligence_engine import detect_space_event
        data = {}
        if request.method == 'POST' and request.get_json(silent=True):
            data = request.get_json(silent=True) or {}
        else:
            iss = get_cached('iss_live', 5, _fetch_iss_live)
            if iss:
                data['iss'] = iss
            try:
                with open(f"{STATION}/static/space_weather.json", 'r', encoding='utf-8') as f:
                    data['solar'] = json.load(f)
            except Exception:
                data['solar'] = {}
            try:
                with open(f"{STATION}/static/voyager_live.json", 'r', encoding='utf-8') as f:
                    data['voyager'] = json.load(f)
            except Exception:
                data['voyager'] = {}
        out = detect_space_event(data)
        return jsonify(out)
    except Exception as e:
        log.warning("api/space/intelligence: %s", e)
        return jsonify({'alerts': [], 'events': [], 'risk_level': 'medium', 'error': str(e)})


@app.route('/space-intelligence-page')
def space_intelligence_page():
    """Page Intelligence spatiale (éviter conflit avec /space)."""
    return render_template('space_intelligence.html')






@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory('static', 'favicon.ico')


# MIGRATED TO main_bp 2026-05-02 (B-RECYCLE R3) — see app/blueprints/main/__init__.py
# @app.route('/about')
# @app.route('/a-propos')
# def about():
#     return render_template('a_propos.html')


# ═══ TÉLESCOPE NASA SKYVIEW ═══════════════════════════════════
from skyview import OBJETS_TLEMCEN, SURVEYS, get_object_image, get_image_url as skyview_get_image_url

@app.route('/telescope')
def telescope():
    return render_template('telescope.html',
                           objets=OBJETS_TLEMCEN,
                           surveys=SURVEYS)

@app.route('/api/telescope/image')
def api_telescope_image():
    """GET /api/telescope/image?objet=M42&survey=DSS2+Red — URL image NASA SkyView."""
    objet  = request.args.get('objet', 'M42')
    survey = request.args.get('survey', 'DSS2 Red')
    data   = get_object_image(objet, survey)
    return jsonify(data)

@app.route('/api/telescope/catalogue')
def api_telescope_catalogue():
    """Liste tous les objets du catalogue Tlemcen."""
    return jsonify({
        "objets":       OBJETS_TLEMCEN,
        "surveys":      SURVEYS,
        "source":       "NASA SkyView",
        "observatoire": "Tlemcen 34.87°N 1.32°E 816m",
    })

@app.route('/api/telescope/proxy-image')
def api_telescope_proxy_image():
    """Proxy NASA SkyView — télécharge l'image côté serveur, évite CORS."""
    import urllib.request as _ureq
    import urllib.parse   as _uparse
    objet  = request.args.get('objet',  'M42')
    survey = request.args.get('survey', 'DSS2 Red')
    pixels = request.args.get('pixels', '600')
    size   = request.args.get('size',   '0.5')
    params = _uparse.urlencode({
        "Position":    objet,
        "Survey":      survey,
        "Coordinates": "J2000",
        "Return":      "GIF",
        "Size":        size,
        "Pixels":      pixels,
        "Scaling":     "Log",
        "resolver":    "SIMBAD-NED",
        "Sampler":     "LI",
        "imscale":     "",
        "skyview":     "query",
    })
    url = f"https://skyview.gsfc.nasa.gov/current/cgi/runquery.pl?{params}"
    try:
        req = _ureq.Request(url, headers={"User-Agent": "AstroScan/2.0 astroscan.space"})
        with _ureq.urlopen(req, timeout=20) as resp:
            data         = resp.read()
            content_type = resp.headers.get_content_type()
        return Response(data,
                        mimetype=content_type or 'image/gif',
                        headers={"Cache-Control": "public, max-age=3600"})
    except Exception as e:
        log.warning("SkyView proxy error: %s", e)
        return Response(status=502)


@app.route('/aladin')
@app.route('/carte-du-ciel')
def aladin_page():
    return render_template('aladin.html')


# Prêt à recevoir du trafic : import Gunicorn/worker terminé (TLE + routes chargés).
server_ready = True



# ── ISS SSE Stream (temps réel sub-5s) ──────────────────
@app.route('/api/iss/stream')
def iss_stream():
    """Stream ISS position via SSE — mise à jour toutes les 3s."""
    def generate():
        import time, json, requests
        while True:
            try:
                r = requests.get("https://api.wheretheiss.at/v1/satellites/25544", timeout=4)
                d = r.json()
                payload = json.dumps({
                    "lat": round(d["latitude"], 4),
                    "lon": round(d["longitude"], 4),
                    "alt": round(d["altitude"], 1),
                    "vel": round(d["velocity"], 1),
                    "ts": int(d["timestamp"]),
                    "vis": d.get("visibility", "unknown"),
                })
                yield f"data: {payload}\n\n"
            except Exception as e:
                yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
            time.sleep(3)
    from flask import Response
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Telescope MJPEG Stream ───────────────────────────────
@app.route('/api/telescope/stream')
def telescope_stream():
    """Stream MJPEG depuis fichier live ou APOD fallback."""
    import time, requests, os
    from flask import Response, stream_with_context

    LIVE_PATH = "/root/astro_scan/telescope_live/current_live.jpg"

    def frames():
        while True:
            try:
                if os.path.exists(LIVE_PATH):
                    mtime = os.path.getmtime(LIVE_PATH)
                    age = time.time() - mtime
                    if age < 300:  # fichier < 5 min = considéré live
                        with open(LIVE_PATH, "rb") as f:
                            img = f.read()
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + img + b"\r\n")
                        time.sleep(2)
                        continue
                # Fallback APOD NASA
                key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
                r = requests.get(f"https://api.nasa.gov/planetary/apod?api_key={key}", timeout=6)
                d = r.json()
                img_url = d.get("url", "")
                if img_url and img_url.endswith((".jpg", ".png", ".jpeg")):
                    img_data = requests.get(img_url, timeout=8).content
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + img_data + b"\r\n")
            except Exception:
                pass
            time.sleep(30)

    return Response(stream_with_context(frames()),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route('/api/telescope/status')
def telescope_status():
    """Statut réel du feed télescope."""
    import time, os
    from flask import jsonify
    LIVE_PATH = "/root/astro_scan/telescope_live/current_live.jpg"
    if os.path.exists(LIVE_PATH):
        age = time.time() - os.path.getmtime(LIVE_PATH)
        mode = "LIVE" if age < 300 else "STALE"
        return jsonify({"mode": mode, "age_sec": int(age), "source": "telescope_live"})
    return jsonify({"mode": "APOD_FALLBACK", "source": "NASA APOD", "note": "Aucune image locale détectée"})

@app.route('/api/stellarium')
def api_stellarium():
    from modules.stellarium_fusion import get_stellarium_data, get_priority_object
    data = get_stellarium_data()
    data["priority_object"] = get_priority_object(data)
    from flask import jsonify
    return jsonify(data)

@app.route('/api/visits/reset', methods=['POST'])
def reset_visits():
    """Reset compteur de visites — admin seulement."""
    try:
        import sqlite3
        db = '/root/astro_scan/data/archive_stellaire.db'
        conn = sqlite3.connect(db)
        old = conn.execute('SELECT count FROM visits WHERE id=1').fetchone()
        conn.execute('UPDATE visits SET count = 0 WHERE id=1')
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'old_count': old[0], 'new_count': 0})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# OWNER IPs — gestion des IPs propriétaire via API
# ══════════════════════════════════════════════════════════════

@app.route('/api/owner-ips', methods=['GET'])
def api_owner_ips_get():
    """Liste les IPs propriétaire (DB + env)."""
    try:
        conn = _get_db_visitors()
        rows = conn.execute(
            "SELECT id, ip, label, added_at FROM owner_ips ORDER BY added_at DESC"
        ).fetchall()
        conn.close()
        result = [{"id": r[0], "ip": r[1], "label": r[2], "added_at": r[3]} for r in rows]
        env_ips = [x.strip() for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(",") if x.strip()]
        return jsonify({"db_ips": result, "env_ips": env_ips})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/owner-ips', methods=['POST'])
def api_owner_ips_add():
    """Ajoute une IP propriétaire. Body JSON: {"ip": "x.x.x.x", "label": "Maison"}"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        ip = (data.get("ip") or "").strip()
        label = (data.get("label") or "")[:100].strip()
        if not ip:
            return jsonify({"ok": False, "error": "ip manquant"}), 400
        conn = _get_db_visitors()
        conn.execute(
            "INSERT OR REPLACE INTO owner_ips (ip, label, added_at) VALUES (?, ?, datetime('now'))",
            (ip, label),
        )
        # Marquer les visites existantes de cette IP comme is_owner=1
        conn.execute("UPDATE visitor_log SET is_owner=1 WHERE ip=?", (ip,))
        conn.commit()
        conn.close()
        _invalidate_owner_ips_cache()
        return jsonify({"ok": True, "ip": ip})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/owner-ips/<int:ip_id>', methods=['DELETE'])
def api_owner_ips_delete(ip_id):
    """Supprime une IP propriétaire par son ID."""
    try:
        conn = _get_db_visitors()
        row = conn.execute("SELECT ip FROM owner_ips WHERE id=?", (ip_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({"ok": False, "error": "IP non trouvée"}), 404
        ip = row[0]
        conn.execute("DELETE FROM owner_ips WHERE id=?", (ip_id,))
        conn.execute("UPDATE visitor_log SET is_owner=0 WHERE ip=?", (ip,))
        conn.commit()
        conn.close()
        _invalidate_owner_ips_cache()
        return jsonify({"ok": True, "removed_ip": ip})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visitor/score-update', methods=['POST'])
def api_visitor_score_update():
    """Beacon JS : met à jour le human_score (JS activé, temps sur page).
    Body JSON: {"session_id": "...", "duration_sec": 45, "js": true}"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        sid = (data.get("session_id") or "")[:128].strip()
        duration = int(data.get("duration_sec") or 0)
        js_active = bool(data.get("js", False))
        if not sid:
            return jsonify({"ok": False}), 400
        conn = _get_db_visitors()
        row = conn.execute(
            "SELECT ip, user_agent FROM visitor_log WHERE session_id=? LIMIT 1", (sid,)
        ).fetchone()
        if row:
            ip, ua = row[0], row[1]
            page_cnt = conn.execute(
                "SELECT COUNT(*) FROM page_views WHERE session_id=?", (sid,)
            ).fetchone()[0]
            referrer = (request.headers.get("Referer") or "")
            score = _compute_human_score(ua or "", page_count=page_cnt,
                                          session_sec=duration, referrer=referrer,
                                          js_beacon=js_active)
            conn.execute(
                "UPDATE visitor_log SET human_score=? WHERE session_id=? AND ip=?",
                (score, sid, ip),
            )
            conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        log.debug("score-update: %s", e)
        return jsonify({"ok": False}), 200


@app.route('/api/analytics/summary', methods=['GET'])
def api_analytics_summary():
    """JSON summary pour dashboard : visiteurs, pages vues, human%, top pages, owner."""
    try:
        conn = _get_db_visitors()
        conn.row_factory = sqlite3.Row

        # KPIs de base
        total_sessions = conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_bot=0 AND is_owner=0"
        ).fetchone()[0]
        total_page_views = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
        unique_ips = conn.execute(
            "SELECT COUNT(DISTINCT ip) FROM visitor_log WHERE is_bot=0 AND is_owner=0"
        ).fetchone()[0]
        bot_count = conn.execute("SELECT COUNT(*) FROM visitor_log WHERE is_bot=1").fetchone()[0]
        human_count = conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_bot=0 AND is_owner=0 AND human_score >= 60"
        ).fetchone()[0]
        owner_count = conn.execute("SELECT COUNT(*) FROM visitor_log WHERE is_owner=1").fetchone()[0]
        avg_score = conn.execute(
            "SELECT ROUND(AVG(human_score),1) FROM visitor_log WHERE is_bot=0 AND is_owner=0 AND human_score >= 0"
        ).fetchone()[0]

        # Top 10 pages
        top_pages = conn.execute(
            "SELECT path, COUNT(*) as cnt FROM page_views WHERE path NOT LIKE '/static%' "
            "GROUP BY path ORDER BY cnt DESC LIMIT 10"
        ).fetchall()

        # Top pays
        top_countries = conn.execute(
            "SELECT country, country_code, COUNT(*) as cnt FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND country != 'Unknown' "
            "GROUP BY country ORDER BY cnt DESC LIMIT 10"
        ).fetchall()

        # Visites owner
        owner_visits = conn.execute(
            "SELECT ip, country, city, isp, MAX(visited_at) as last_visit, COUNT(*) as sessions "
            "FROM visitor_log WHERE is_owner=1 GROUP BY ip ORDER BY last_visit DESC LIMIT 20"
        ).fetchall()

        conn.close()

        human_pct = round(100 * human_count / max(1, total_sessions), 1)
        bot_pct = round(100 * bot_count / max(1, total_sessions + bot_count), 1)

        return jsonify({
            "total_sessions": int(total_sessions),
            "total_page_views": int(total_page_views),
            "unique_ips": int(unique_ips),
            "bot_count": int(bot_count),
            "human_count": int(human_count),
            "owner_count": int(owner_count),
            "human_pct": float(human_pct),
            "bot_pct": float(bot_pct),
            "avg_human_score": float(avg_score or 0),
            "top_pages": [{"path": r["path"], "count": r["cnt"]} for r in top_pages],
            "top_countries": [{"country": r["country"], "code": r["country_code"], "count": r["cnt"]} for r in top_countries],
            "owner_visits": [
                {"ip": r["ip"], "country": r["country"], "city": r["city"],
                 "isp": r["isp"], "last_visit": r["last_visit"], "sessions": r["sessions"]}
                for r in owner_visits
            ],
        })
    except Exception as e:
        log.warning("api_analytics_summary: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/visits/count')
def get_visits():
    """Retourne le compteur de visites actuel."""
    try:
        import sqlite3
        db = '/root/astro_scan/data/archive_stellaire.db'
        conn = sqlite3.connect(db)
        row = conn.execute('SELECT count FROM visits WHERE id=1').fetchone()
        conn.close()
        return jsonify({'count': row[0] if row else 0})
    except Exception as e:
        return jsonify({'count': 0, 'error': str(e)})

# ── GEO-IP TRACKER ───────────────────────────────────────
import sqlite3 as _sqlite3

def _get_db_visitors():
    return _sqlite3.connect("/root/astro_scan/data/archive_stellaire.db")


@app.route("/api/visitors/globe-data")
def api_visitors_globe_data():
    """Points carte (Leaflet) pour /visiteurs-live — agrégation par pays."""
    try:
        exclude_my_ip = (request.args.get("exclude_my_ip", "1") or "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        p = get_global_stats(exclude_my_ip=exclude_my_ip)
        return jsonify({"ok": True, "points": p.get("points") or []})
    except Exception as e:
        log.warning("visitors/globe-data: %s", e)
        return jsonify({"ok": False, "points": [], "error": str(e)})


@app.route("/api/visitors/snapshot")
def api_visitors_snapshot():
    """REST one-shot : même payload que le SSE — utilisé pour le polling fallback."""
    try:
        exclude_my_ip = (request.args.get("exclude_my_ip", "1") or "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        return jsonify(get_global_stats(exclude_my_ip=exclude_my_ip))
    except Exception as e:
        log.warning("visitors/snapshot: %s", e)
        return jsonify({"error": str(e), "total": 0, "online_now": 0, "top_countries": [],
                        "last_connections": [], "heatmap": [], "humans_total": 0,
                        "bots_total": 0, "humans_today": 0})


@app.route("/api/visitors/stream")
def api_visitors_stream():
    """SSE : stats live pour la page Visiteurs LIVE (rafraîchissement périodique)."""
    exclude_my_ip = (request.args.get("exclude_my_ip", "1") or "0").strip().lower() in (
        "1", "true", "yes", "on",
    )

    def gen():
        while True:
            try:
                payload = get_global_stats(exclude_my_ip=exclude_my_ip)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as e:
                err = {"error": str(e), "total": 0, "online_now": 0, "top_countries": [],
                       "last_connections": [], "heatmap": [], "humans_total": 0,
                       "bots_total": 0, "humans_today": 0}
                yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield ": keepalive\n\n"
            time.sleep(8)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _log_visitor(request):
    """Enregistre un visiteur avec son IP et chemin."""
    try:
        _register_unique_visit_from_request(path_override=request.path)
    except Exception:
        pass

@app.route("/api/visitors/log", methods=["POST"])
def api_log_visitor():
    """Log un visiteur depuis le frontend."""
    try:
        data = request.get_json(silent=True) or {}
        path = data.get("path", "/")
        tracked = _register_unique_visit_from_request(path_override=path)
        return jsonify({"ok": True, "tracked": bool(tracked)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/visitors/geo")
def api_visitors_geo():
    """Retourne les derniers visiteurs avec geolocalisation live."""
    import requests as _req
    try:
        # switch test/prod: ?exclude_my_ip=1 (default: include)
        my_ip = "105.235.139.99"
        exclude_my_ip = (request.args.get("exclude_my_ip", "0") or "0").strip() in ("1", "true", "yes", "on")
        excluded = {"127.0.0.1", "::1"}
        if exclude_my_ip:
            excluded.add(my_ip)
        placeholders = ",".join(["?"] * len(excluded))
        params = tuple(excluded)
        conn = _get_db_visitors()
        rows = conn.execute(
            "SELECT id, ip, country, country_code, city, region, flag, path, visited_at "
            "FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) "
            "ORDER BY id DESC LIMIT 50",
            params
        ).fetchall()
        conn.close()
        visitors = []
        ips_to_resolve = []
        for row in rows:
            v = {
                "id": row[0], "ip": row[1], "country": row[2],
                "country_code": row[3], "city": row[4], "region": row[5],
                "flag": row[6], "path": row[7], "visited_at": row[8]
            }
            if v["country"] == "Unknown" and v["ip"] not in ("127.0.0.1", "::1"):
                ips_to_resolve.append(v["ip"])
            visitors.append(v)

        # Résoudre IPs inconnues via ip-api.com (gratuit, 1000 req/min)
        resolved = {}
        unique_ips = list(set(ips_to_resolve))[:10]
        for ip in unique_ips:
            try:
                r = _req.get(
                    f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,regionName",
                    timeout=3
                )
                d = r.json()
                if d.get("status") == "success":
                    code = d.get("countryCode", "XX")
                    resolved[ip] = {
                        "country": d.get("country", "Unknown"),
                        "country_code": code,
                        "city": d.get("city", "Unknown"),
                        "region": d.get("regionName", "Unknown"),
                        "flag": code
                    }
            except Exception:
                pass

        # Mettre à jour la DB avec les nouvelles résolutions
        if resolved:
            conn2 = _get_db_visitors()
            for ip, geo in resolved.items():
                conn2.execute(
                    "UPDATE visitor_log SET country=?, country_code=?, city=?, region=?, flag=? WHERE ip=? AND country='Unknown'",
                    (geo["country"], geo["country_code"], geo["city"], geo["region"], geo["flag"], ip)
                )
            conn2.commit()
            conn2.close()

            # Mettre à jour la réponse
            for v in visitors:
                if v["ip"] in resolved:
                    v.update(resolved[v["ip"]])

        return jsonify({"visitors": visitors, "total": len(visitors)})
    except Exception as e:
        return jsonify({"visitors": [], "error": str(e)})

@app.route("/api/visitors/stats")
def api_visitors_stats():
    """Statistiques visiteurs par pays."""
    try:
        # switch test/prod: ?exclude_my_ip=1 (default: include)
        my_ip = "105.235.139.99"
        exclude_my_ip = (request.args.get("exclude_my_ip", "0") or "0").strip() in ("1", "true", "yes", "on")
        excluded = {"127.0.0.1", "::1"}
        if exclude_my_ip:
            excluded.add(my_ip)
        placeholders = ",".join(["?"] * len(excluded))
        params = tuple(excluded)
        conn = _get_db_visitors()
        by_country = conn.execute(
            "SELECT country, country_code, COUNT(*) as cnt "
            "FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) AND country != 'Unknown' "
            "GROUP BY country, country_code "
            "ORDER BY cnt DESC LIMIT 50",
            params
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM visitor_log WHERE ip NOT IN ({placeholders})",
            params
        ).fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) AND date(visited_at)=date('now')",
            params
        ).fetchone()[0]
        conn.close()
        return jsonify({
            "total": total,
            "today": today,
            "exclude_my_ip": exclude_my_ip,
            "by_country": [
                {"country": r[0], "code": r[1] or "XX", "count": r[2]}
                for r in by_country
                if (r[1] or "XX").upper() != "XX" and "inconnu" not in (r[0] or "").lower()
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/visitors/connection-time")
def api_visitors_connection_time_legacy():
    """Redirige 301 vers la version underscore (URL canonique)."""
    return redirect("/api/visitors/connection_time", code=301)


@app.route("/api/visitors/connection_time")
def api_visitors_connection_time():
    """Temps de connexion par IP (visiteurs externes), dédupliqué et plafonné."""
    try:
        def _parse_visitor_at(ts):
            """Parse visited_at SQLite / ISO pour estimation de durée (fallback)."""
            s = (ts or "").strip()
            if not s:
                return None
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            if "T" in s:
                try:
                    return datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:
                    pass
            try:
                return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return None

        fallback_my_ip = "105.235.139.99"
        env_owner_ips = (os.environ.get("ASTROSCAN_OWNER_IPS") or "").strip()
        if env_owner_ips:
            owner_ips = {x.strip() for x in env_owner_ips.split(",") if x.strip()}
        else:
            owner_ips = set()
        single_owner = (os.environ.get("ASTROSCAN_MY_IP") or "").strip()
        if single_owner:
            owner_ips.add(single_owner)
        if not owner_ips:
            owner_ips.add(fallback_my_ip)
        # Étend "MON IP" aux IP qui partagent les mêmes session_id
        # (cas fréquent mobile/fibre/CGNAT chez le même utilisateur).
        related_owner_ips = set()
        try:
            conn_owner = _get_db_visitors()
            conn_owner.row_factory = sqlite3.Row
            owner_list = sorted(owner_ips)
            owner_ph = ",".join(["?"] * len(owner_list))
            sid_rows = conn_owner.execute(
                "SELECT DISTINCT session_id FROM visitor_log "
                f"WHERE ip IN ({owner_ph}) AND COALESCE(session_id,'')<>''",
                tuple(owner_list),
            ).fetchall()
            sids = [str(r["session_id"]).strip() for r in sid_rows if r["session_id"]]
            if sids:
                sid_ph = ",".join(["?"] * len(sids))
                ip_rows = conn_owner.execute(
                    "SELECT DISTINCT ip FROM visitor_log "
                    f"WHERE session_id IN ({sid_ph}) AND COALESCE(ip,'')<>''",
                    tuple(sids),
                ).fetchall()
                for r in ip_rows:
                    ip = str(r["ip"]).strip()
                    if ip:
                        related_owner_ips.add(ip)
            conn_owner.close()
        except Exception:
            related_owner_ips = set()
        effective_owner_ips = set(owner_ips) | set(related_owner_ips)
        exclude_my_ip = (request.args.get("exclude_my_ip", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
        excluded = {"127.0.0.1", "::1"}
        if exclude_my_ip:
            excluded.update(effective_owner_ips)
        placeholders = ",".join(["?"] * len(excluded))
        base_params = tuple(excluded)

        conn = _get_db_visitors()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ip, "
            "COALESCE(country,'Unknown') AS country, "
            "COALESCE(city,'Unknown') AS city, "
            "COALESCE(country_code,'XX') AS country_code, "
            "COALESCE(session_id,'') AS session_id, "
            "COALESCE(visited_at,'') AS visited_at "
            "FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) "
            "ORDER BY id DESC",
            base_params,
        ).fetchall()

        by_ip = {}
        session_ip_hits = {}
        for r in rows:
            ip = (r["ip"] or "").strip()
            if not ip:
                continue
            entry = by_ip.get(ip)
            vis_at = (r["visited_at"] or "").strip()
            if not entry:
                entry = {
                    "ip": ip,
                    "country": r["country"] or "Unknown",
                    "city": r["city"] or "Unknown",
                    "country_code": r["country_code"] or "XX",
                    "sessions": set(),
                    "session_count": 0,
                    "total_sec": 0,
                    "last_visit": vis_at,
                    "first_visit": vis_at,
                    "visit_count": 0,
                }
                by_ip[ip] = entry
            else:
                # Dernière visite = max (chaînes ISO triables pour les formats habituels)
                if vis_at and (not entry["last_visit"] or vis_at > entry["last_visit"]):
                    entry["last_visit"] = vis_at
                if vis_at and (not entry.get("first_visit") or vis_at < entry["first_visit"]):
                    entry["first_visit"] = vis_at
            entry["visit_count"] = int(entry.get("visit_count") or 0) + 1
            sid = (r["session_id"] or "").strip()
            if sid:
                entry["sessions"].add(sid)
                hit_map = session_ip_hits.get(sid)
                if not hit_map:
                    hit_map = {}
                    session_ip_hits[sid] = hit_map
                hit_map[ip] = int(hit_map.get(ip, 0)) + 1

        # Répartition robuste:
        # - calcule la durée réelle d'une session une seule fois (cap span)
        # - distribue proportionnellement aux hits IP de cette session
        all_sids = list(session_ip_hits.keys())
        sid_totals = {}
        if all_sids:
            chunk = 500
            for i in range(0, len(all_sids), chunk):
                batch = all_sids[i : i + chunk]
                sid_ph = ",".join(["?"] * len(batch))
                t_rows = conn.execute(
                    "SELECT session_id, "
                    "COALESCE(SUM(duration),0) AS total_duration, "
                    "MIN(created_at) AS first_at, "
                    "MAX(created_at) AS last_at "
                    "FROM session_time "
                    f"WHERE session_id IN ({sid_ph}) "
                    "GROUP BY session_id",
                    tuple(batch),
                ).fetchall()
                for tr in t_rows:
                    sid = (tr["session_id"] or "").strip()
                    if not sid:
                        continue
                    total_sec = int(tr["total_duration"] or 0)
                    span_sec = 0
                    if tr["first_at"] and tr["last_at"]:
                        try:
                            dt0 = datetime.fromisoformat(str(tr["first_at"]).replace("Z", "+00:00"))
                            dt1 = datetime.fromisoformat(str(tr["last_at"]).replace("Z", "+00:00"))
                            span_sec = max(0, int((dt1 - dt0).total_seconds()))
                        except Exception:
                            span_sec = 0
                    if span_sec > 0:
                        total_sec = min(total_sec, span_sec)
                    sid_totals[sid] = max(0, min(total_sec, 86400 * 7))

        for entry in by_ip.values():
            sc = len(entry["sessions"])
            if sc <= 0 and int(entry.get("visit_count") or 0) > 0:
                sc = 1
            entry["session_count"] = sc
            entry["total_sec"] = 0

        for sid, hit_map in session_ip_hits.items():
            total = int(sid_totals.get(sid, 0))
            if total <= 0:
                continue
            denom = sum(int(v or 0) for v in hit_map.values())
            if denom <= 0:
                continue
            allocated = 0
            keys = list(hit_map.keys())
            for idx, ip in enumerate(keys):
                share = int(round(total * (int(hit_map[ip]) / float(denom))))
                if idx == len(keys) - 1:
                    share = max(0, total - allocated)
                allocated += share
                if ip in by_ip:
                    by_ip[ip]["total_sec"] += max(0, share)

        # Fallback : si session_time est vide (sendBeacon/pagehide peu fiables, iframe, mobile),
        # estimer une durée minimale par fenêtre first_visit → last_visit dans visitor_log.
        for entry in by_ip.values():
            if int(entry.get("total_sec") or 0) > 0:
                continue
            fv = entry.get("first_visit") or ""
            lv = entry.get("last_visit") or ""
            dt0 = _parse_visitor_at(fv)
            dt1 = _parse_visitor_at(lv)
            if dt0 and dt1:
                est = max(0, int((dt1 - dt0).total_seconds()))
                if est <= 0 and int(entry.get("visit_count") or 0) > 0:
                    est = 1
                entry["total_sec"] = min(est, 86400 * 7)

        conn.close()

        def _fmt_duration(sec):
            sec = int(sec or 0)
            h, rem = divmod(sec, 3600)
            m, s = divmod(rem, 60)
            if h > 0:
                return f"{h}h{m:02d}m{s:02d}"
            if m > 0:
                return f"{m} min {s} s"
            return f"{s} s"

        def _level(sec):
            if sec >= 180:
                return "FORT"
            if sec >= 30:
                return "MOYEN"
            return "FAIBLE"

        items = []
        for v in by_ip.values():
            is_my_ip = False if exclude_my_ip else (v["ip"] in effective_owner_ips)
            items.append({
                "ip": v["ip"],
                "country": v["country"],
                "city": v["city"],
                "country_code": v["country_code"],
                "sessions": v["session_count"],
                "total_sec": v["total_sec"],
                "total_time": _fmt_duration(v["total_sec"]),
                "level": _level(v["total_sec"]),
                "last_visit": v["last_visit"],
                "is_my_ip": is_my_ip,
                "traffic_segment": "owner_test" if is_my_ip else "external_visitor",
            })

        items.sort(
            key=lambda x: (x.get("last_visit") or "", x["total_sec"], x["sessions"]),
            reverse=True,
        )
        my_items = [x for x in items if x.get("is_my_ip")]
        ext_items = [x for x in items if not x.get("is_my_ip")]
        my_total_sec = sum(int(x.get("total_sec") or 0) for x in my_items)
        ext_total_sec = sum(int(x.get("total_sec") or 0) for x in ext_items)
        resp = jsonify({
            "ok": True,
            "exclude_my_ip": exclude_my_ip,
            "my_ip": sorted(owner_ips)[0] if owner_ips else fallback_my_ip,
            "owner_ips": sorted(owner_ips),
            "effective_owner_ips": sorted(effective_owner_ips),
            "total_ips": len(items),
            "my_ip_count": len(my_items),
            "external_ip_count": len(ext_items),
            "my_total_sec": my_total_sec,
            "external_total_sec": ext_total_sec,
            "items": items[:100],
        })
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "items": []}), 500


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


@app.route("/track-time", methods=["POST"])
def track_time_endpoint():
    """Enregistre la durée passée sur une page pour une session (sendBeacon / fetch)."""
    try:
        data = request.get_json(silent=True) or {}
        sid = (data.get("session_id") or request.cookies.get("astroscan_sid") or "")[:128]
        path = (data.get("path") or "")[:500]
        try:
            duration = int(data.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0
        if duration < 0:
            duration = 0
        if duration > 86400:
            duration = 86400
        if not sid:
            return jsonify({"ok": False, "error": "no session"}), 400
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO session_time (session_id, path, duration, created_at) VALUES (?, ?, ?, ?)",
            (sid, path, duration, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"ok": False}), 500


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

_HIJRI_MONTHS = [
    'Mouharram','Safar','Rabi al-Awwal','Rabi al-Thani',
    'Joumada al-Oula','Joumada al-Thania','Rajab','Chaabane',
    'Ramadan','Chawwal','Dhou al-Qi\'da','Dhou al-Hijja'
]

def _hilal_compute(for_date=None):
    """
    Calcule la visibilité du croissant islamique pour Tlemcen.
    Retourne un dict complet avec critères ODEH, UIOF et Oum Al Qura.
    """
    import math
    import ephem
    from datetime import timedelta
    from astropy.coordinates import (EarthLocation, AltAz, get_body, get_sun,
                                     solar_system_ephemeris)
    from astropy.time import Time
    import astropy.units as u

    LAT, LON, ALT = 34.87, 1.32, 800
    location = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ALT * u.m)

    # Date de référence
    if for_date is None:
        for_date = datetime.now(timezone.utc).date()

    # ── 1. Trouver la prochaine nouvelle lune ──
    obs = ephem.Observer()
    obs.lat = str(LAT)
    obs.lon = str(LON)
    obs.elevation = ALT
    obs.pressure = 0
    obs.horizon = '-0:34'

    ref_dt = datetime(for_date.year, for_date.month, for_date.day, 12, 0, 0)
    obs.date = ref_dt.strftime('%Y/%m/%d %H:%M:%S')

    next_new = ephem.next_new_moon(obs.date)
    next_new_dt = next_new.datetime().replace(tzinfo=timezone.utc)

    # ── 2. Coucher du soleil le jour J et J+1 après la nouvelle lune ──
    def find_sunset(day):
        """Retourne l'heure du coucher soleil (UTC) pour un jour donné."""
        obs2 = ephem.Observer()
        obs2.lat = str(LAT)
        obs2.lon = str(LON)
        obs2.elevation = ALT
        obs2.pressure = 1013
        obs2.horizon = '-0:50'  # réfraction
        obs2.date = f"{day.year}/{day.month:02d}/{day.day:02d} 12:00:00"
        try:
            sunset_ephem = obs2.next_setting(ephem.Sun())
            return sunset_ephem.datetime().replace(tzinfo=timezone.utc)
        except Exception:
            return datetime(day.year, day.month, day.day, 18, 30, tzinfo=timezone.utc)

    # Jour de la nouvelle lune et lendemain
    nm_day = next_new_dt.date()
    days_to_check = [nm_day, nm_day + timedelta(days=1)]

    results_by_day = []
    for check_day in days_to_check:
        sunset_dt = find_sunset(check_day)
        t_sunset = Time(sunset_dt)

        frame = AltAz(obstime=t_sunset, location=location)
        moon_coord = get_body('moon', t_sunset).transform_to(frame)
        sun_coord = get_sun(t_sunset).transform_to(frame)

        moon_alt = float(moon_coord.alt.deg)
        moon_az = float(moon_coord.az.deg)
        sun_alt = float(sun_coord.alt.deg)

        # Elongation géocentrique (ARCL)
        with solar_system_ephemeris.set('builtin'):
            moon_gcrs = get_body('moon', t_sunset)
            sun_gcrs = get_sun(t_sunset)
        arcl_deg = float(moon_gcrs.separation(sun_gcrs).deg)

        # ARCV = altitude de la lune au coucher du soleil
        arcv_deg = moon_alt

        # Largeur du croissant (W) en minutes d'arc — formule Odeh
        # W = 0.27245 * SD * (1 - cos(ARCL))  où SD = demi-diamètre moyen ≈ 0.2725°
        crescent_w_deg = 0.27245 * (1.0 - math.cos(math.radians(arcl_deg)))
        crescent_w_arcmin = crescent_w_deg * 60.0

        # Âge lunaire depuis la nouvelle lune (heures)
        moon_age_h = (sunset_dt - next_new_dt).total_seconds() / 3600.0

        # ── Critère ODEH (2006) ──
        # Visible si ARCL ≥ 6.4° ET W ≥ 0.216°
        # Incertain si ARCL ≥ 6.4° ET W ≥ 0.1°
        if arcl_deg >= 6.4 and crescent_w_deg >= 0.216:
            odeh = 'VISIBLE'
        elif arcl_deg >= 6.4 and crescent_w_deg >= 0.1:
            odeh = 'INCERTAIN'
        elif moon_alt > 0 and moon_age_h >= 15:
            odeh = 'POSSIBLE'
        else:
            odeh = 'NON VISIBLE'

        # ── Critère UIOF / France ──
        # Lune visible si altitude > 3° au coucher du soleil ET Âge > 15h
        if arcv_deg >= 5.0 and moon_age_h >= 15:
            uiof = 'VISIBLE'
        elif arcv_deg >= 3.0 and moon_age_h >= 12:
            uiof = 'INCERTAIN'
        else:
            uiof = 'NON VISIBLE'

        # ── Critère Oum Al Qura (Arabie Saoudite) ──
        # Lune visible si elle se couche APRÈS le soleil ET lune couchée ≥ 5 min après soleil
        obs3 = ephem.Observer()
        obs3.lat = str(LAT); obs3.lon = str(LON); obs3.elevation = ALT
        obs3.pressure = 1013; obs3.horizon = '-0:50'
        obs3.date = f"{check_day.year}/{check_day.month:02d}/{check_day.day:02d} 12:00:00"
        try:
            moonset_ephem = obs3.next_setting(ephem.Moon())
            moonset_dt = moonset_ephem.datetime().replace(tzinfo=timezone.utc)
            lag_min = (moonset_dt - sunset_dt).total_seconds() / 60.0
            oumqura = 'VISIBLE' if lag_min >= 5 and moon_alt > 0 else 'NON VISIBLE'
        except Exception:
            oumqura = 'INCERTAIN'
            lag_min = 0.0

        # Coucher de la lune
        try:
            moonset_str = moonset_dt.strftime('%H:%M UTC') if 'moonset_dt' in dir() else '—'
        except Exception:
            moonset_str = '—'

        results_by_day.append({
            'date': check_day.isoformat(),
            'sunset_utc': sunset_dt.strftime('%H:%M UTC'),
            'moonset_utc': moonset_str,
            'moon_alt_deg': round(arcv_deg, 2),
            'moon_az_deg': round(moon_az, 2),
            'arcl_deg': round(arcl_deg, 2),
            'arcv_deg': round(arcv_deg, 2),
            'crescent_width_arcmin': round(crescent_w_arcmin, 3),
            'crescent_width_deg': round(crescent_w_deg, 4),
            'moon_age_hours': round(max(0, moon_age_h), 1),
            'criteria': {
                'odeh': odeh,
                'uiof': uiof,
                'oum_al_qura': oumqura,
            },
            'moonset_lag_min': round(lag_min, 1) if 'lag_min' in dir() else None,
        })

    # ── 3. Mois hégirien approximatif ──
    # Comptage depuis 1 Mouharram 1 AH = 16 juillet 622 CE
    J0 = 1948439.5  # JD du 1 Mouharram 1 AH (approx)
    jd_now = Time(datetime.now(timezone.utc)).jd
    hijri_days = jd_now - J0
    hijri_months_total = hijri_days / 29.53058867
    hijri_year = int(hijri_months_total / 12) + 1
    hijri_month_idx = int(hijri_months_total % 12)
    hijri_month_name = _HIJRI_MONTHS[hijri_month_idx % 12]
    hijri_day = int((hijri_months_total % 1) * 29.53) + 1

    # ── 4. Compte à rebours jusqu'au premier jour possible ──
    best_day = None
    best_criteria = 'NON VISIBLE'
    for r in results_by_day:
        if r['criteria']['odeh'] in ('VISIBLE', 'INCERTAIN') or \
           r['criteria']['uiof'] in ('VISIBLE', 'INCERTAIN'):
            best_day = r['date']
            best_criteria = r['criteria']
            break
    if best_day is None:
        best_day = results_by_day[-1]['date'] if results_by_day else (nm_day + timedelta(days=1)).isoformat()

    delta_days = (datetime.fromisoformat(best_day).date() - for_date).days

    return {
        'ok': True,
        'computed_at': datetime.now(timezone.utc).isoformat(),
        'location': {'city': 'Tlemcen', 'lat': LAT, 'lon': LON, 'alt_m': ALT},
        'hijri_current': {
            'year': hijri_year,
            'month_num': hijri_month_idx + 1,
            'month_name': hijri_month_name,
            'day': hijri_day,
        },
        'new_moon': {
            'datetime_utc': next_new_dt.isoformat(),
            'date': nm_day.isoformat(),
        },
        'sighting_days': results_by_day,
        'predicted_first_day': best_day,
        'countdown_days': delta_days,
        'next_month_name': _HIJRI_MONTHS[(hijri_month_idx + 1) % 12],
        'next_hijri_year': hijri_year + (1 if hijri_month_idx == 11 else 0),
    }


def _hilal_compute_calendar():
    """
    Génère le calendrier hégire pour les 24 prochains mois.
    Critères : ODEH 2006 (principal) + Istanbul 1978 / IRCICA (secondaire).
    Cache 24h recommandé (données stables).
    """
    import math
    import ephem
    from datetime import timedelta

    LAT, LON, ALT = 34.8700, 1.3200, 816   # Tlemcen précis

    now   = datetime.now(timezone.utc)
    today = now.date()

    # ── Mois hégire courant (même formule que _hilal_compute) ──
    J0 = 1948439.5
    from astropy.time import Time as _ATime
    jd_now              = _ATime(now).jd
    total_months        = int((jd_now - J0) / 29.53058867)
    h_year_base         = total_months // 12 + 1
    h_month_idx_base    = total_months % 12          # 0-indexed, mois courant

    # ── Helpers ephem ──
    def _obs(day, pressure=1013, horizon='-0:50'):
        o = ephem.Observer()
        o.lat = str(LAT); o.lon = str(LON)
        o.elevation = ALT; o.pressure = pressure; o.horizon = horizon
        o.date = f'{day.year}/{day.month:02d}/{day.day:02d} 12:00:00'
        return o

    def _sunset(day):
        try:
            return _obs(day).next_setting(ephem.Sun()).datetime().replace(tzinfo=timezone.utc)
        except Exception:
            return datetime(day.year, day.month, day.day, 18, 30, tzinfo=timezone.utc)

    def _sighting(check_day, nm_dt):
        sunset_dt = _sunset(check_day)

        # Position lune + soleil au moment du coucher du soleil
        o2 = ephem.Observer()
        o2.lat = str(LAT); o2.lon = str(LON)
        o2.elevation = ALT; o2.pressure = 1013; o2.horizon = '-0:34'
        o2.date = ephem.Date(sunset_dt.strftime('%Y/%m/%d %H:%M:%S'))

        moon = ephem.Moon(); sun_obj = ephem.Sun()
        moon.compute(o2); sun_obj.compute(o2)

        moon_alt = math.degrees(moon.alt)
        arcl_deg = math.degrees(ephem.separation(moon, sun_obj))

        crescent_w_deg    = 0.27245 * (1.0 - math.cos(math.radians(arcl_deg)))
        crescent_w_arcmin = crescent_w_deg * 60.0
        moon_age_h        = max(0.0, (sunset_dt - nm_dt).total_seconds() / 3600.0)

        # Coucher lune + lag
        o3 = _obs(check_day, pressure=1013, horizon='-0:34')
        try:
            moonset_dt  = o3.next_setting(ephem.Moon()).datetime().replace(tzinfo=timezone.utc)
            lag_min     = (moonset_dt - sunset_dt).total_seconds() / 60.0
            moonset_str = moonset_dt.strftime('%H:%M UTC')
        except Exception:
            lag_min = 0.0; moonset_str = '—'

        # ODEH 2006 — critère international de référence
        if arcl_deg >= 6.4 and crescent_w_deg >= 0.216:
            odeh = 'VISIBLE'
        elif arcl_deg >= 6.4 and crescent_w_deg >= 0.1:
            odeh = 'INCERTAIN'
        elif moon_alt > 0 and moon_age_h >= 15:
            odeh = 'POSSIBLE'
        else:
            odeh = 'NON VISIBLE'

        # Istanbul 1978 — IRCICA : alt ≥ 5° + arcl ≥ 8° + âge ≥ 15h
        if moon_alt >= 5.0 and arcl_deg >= 8.0 and moon_age_h >= 15:
            istanbul = 'VISIBLE'
        elif moon_alt >= 3.0 and arcl_deg >= 6.0 and moon_age_h >= 12:
            istanbul = 'INCERTAIN'
        else:
            istanbul = 'NON VISIBLE'

        # Oum Al Qura — moonset lag ≥ 5 min
        oumqura = 'VISIBLE' if lag_min >= 5 and moon_alt > 0 else 'NON VISIBLE'

        return {
            'date':                 check_day.isoformat(),
            'sunset_utc':           sunset_dt.strftime('%H:%M UTC'),
            'moonset_utc':          moonset_str,
            'arcl_deg':             round(arcl_deg, 2),
            'arcv_deg':             round(moon_alt, 2),
            'crescent_width_arcmin': round(crescent_w_arcmin, 3),
            'moon_age_hours':       round(moon_age_h, 1),
            'moonset_lag_min':      round(lag_min, 1),
            'criteria': {'odeh': odeh, 'istanbul': istanbul, 'oum_al_qura': oumqura},
        }

    def _pick_first(days):
        # Priorité ODEH VISIBLE → Istanbul VISIBLE → INCERTAIN → J+1 par défaut
        for d in days:
            if d['criteria']['odeh'] == 'VISIBLE':
                return d['date'], d['criteria'], 'ODEH'
        for d in days:
            if d['criteria']['istanbul'] == 'VISIBLE':
                return d['date'], d['criteria'], 'Istanbul'
        for d in days:
            if d['criteria']['odeh'] in ('INCERTAIN', 'POSSIBLE') or \
               d['criteria']['istanbul'] == 'INCERTAIN':
                return d['date'], d['criteria'], 'calcul'
        return days[-1]['date'], days[-1]['criteria'], 'astronomique'

    def _badge(crit):
        o = crit.get('odeh', ''); i = crit.get('istanbul', '')
        if o == 'VISIBLE' and i == 'VISIBLE':   return 'CONFIRMÉ',  95
        if o == 'VISIBLE':                        return 'PROBABLE',  85
        if i == 'VISIBLE':                        return 'PROBABLE',  78
        if o in ('INCERTAIN', 'POSSIBLE') or i == 'INCERTAIN':
                                                  return 'INCERTAIN', 60
        return 'CALCUL', 30

    # ── Boucle 24 nouvelles lunes ──
    search_dt   = now
    h_year      = h_year_base
    h_month_idx = h_month_idx_base
    calendar    = []

    for _ in range(24):
        o_nm = ephem.Observer()
        o_nm.lat = str(LAT); o_nm.lon = str(LON)
        o_nm.elevation = ALT; o_nm.pressure = 0
        o_nm.date = search_dt.strftime('%Y/%m/%d %H:%M:%S')

        nm_ephem = ephem.next_new_moon(o_nm.date)
        nm_dt    = nm_ephem.datetime().replace(tzinfo=timezone.utc)
        nm_day   = nm_dt.date()

        sighting = [_sighting(nm_day + timedelta(days=off), nm_dt) for off in range(2)]
        first_day_str, first_crit, method = _pick_first(sighting)
        badge, pct = _badge(first_crit)

        # Avancer le compteur hégire
        h_month_idx = (h_month_idx + 1) % 12
        if h_month_idx == 0:
            h_year += 1

        month_name = _HIJRI_MONTHS[h_month_idx]
        calendar.append({
            'hijri_month_num':    h_month_idx + 1,
            'hijri_month_name':   month_name,
            'hijri_year':         h_year,
            'date_1er_gregorien': first_day_str,
            'new_moon_utc':       nm_dt.isoformat(),
            'badge':              badge,
            'certitude_pct':      pct,
            'method':             method,
            'criteria':           first_crit,
            'sighting_days':      sighting,
            'is_ramadan':         h_month_idx == 8,
            'is_aid_fitr':        h_month_idx == 9,
            'is_aid_adha':        h_month_idx == 11,
        })

        search_dt = nm_dt + timedelta(days=29)

    # Prochain Ramadan + compte à rebours
    next_ramadan = next((m for m in calendar if m['is_ramadan']), None)
    countdown_ramadan = None
    if next_ramadan:
        rd = datetime.fromisoformat(next_ramadan['date_1er_gregorien']).date()
        countdown_ramadan = (rd - today).days

    return {
        'ok':           True,
        'computed_at':  now.isoformat(),
        'location':     {'city': 'Tlemcen', 'lat': LAT, 'lon': LON, 'alt_m': ALT},
        'ephemeris':    'VSOP87 / Méeus (ephem) + DE430 (astropy)',
        'criteria_info': {
            'primary':   'ODEH 2006 — International Astronomical Center',
            'secondary': 'Istanbul 1978 — IRCICA (alt ≥ 5° + arcl ≥ 8° + âge ≥ 15h)',
            'note':      'Précision ±1 jour · Tlemcen 34.87°N 1.32°E 816m · Cache 24h',
        },
        'calendar':               calendar,
        'next_ramadan':           next_ramadan,
        'countdown_ramadan_days': countdown_ramadan,
    }


@app.route('/api/hilal/calendar')
def api_hilal_calendar():
    """Calendrier hégire 24 mois — ODEH 2006 + Istanbul 1978. Cache 24h."""
    cached = cache_get('hilal_calendar', 86400)
    if cached is not None:
        return jsonify(cached)
    try:
        data = _hilal_compute_calendar()
        cache_set('hilal_calendar', data)
        return jsonify(data)
    except Exception as e:
        log.error('api_hilal_calendar: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/hilal')
def api_hilal():
    """Calcul du croissant islamique (Hilal) pour Tlemcen. Cache 30 min."""
    cached = cache_get('hilal_data', 1800)
    if cached is not None:
        return jsonify(cached)
    try:
        data = _hilal_compute()
        cache_set('hilal_data', data)
        return jsonify(data)
    except Exception as e:
        log.error('api_hilal: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500



# MIGRATED TO iss_bp 2026-05-02 (B3b) — see app/blueprints/iss/routes.py
# @app.route('/orbital')
# def orbital_dashboard():
#     return render_template('orbital_dashboard.html')


import requests
from datetime import datetime

@app.route('/api/meteo/reel')
def meteo_reel():
    try:
        # Ville par défaut (modifiable)
        city = request.args.get('city', 'Tlemcen')

        url = f"https://wttr.in/{city}?format=j1"
        r = requests.get(url, timeout=5)
        data = r.json()

        current = data['current_condition'][0]

        return jsonify({
            "city": city,
            "temp": current['temp_C'],
            "humidity": current['humidity'],
            "wind": current['windspeedKmph'],
            "desc": current['weatherDesc'][0]['value'],
            "time": datetime.utcnow().isoformat(),
            "ok": True
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/meteo-reel')
def meteo_page():
    return render_template('meteo_reel.html')




@app.route('/control')
@app.route('/meteo')
def control():
    return render_template('orbital_control_center.html')


def _compute_ephemerides_tlemcen_astropy():
    """
    Éphémérides journalières pour Tlemcen (UTC) via astropy.
    Corps: Soleil, Lune, Jupiter, Mars, Saturne, Vénus.
    """
    from astropy.coordinates import EarthLocation, AltAz, get_body
    from astropy.time import Time
    import astropy.units as u

    location = EarthLocation(lat=34.8731 * u.deg, lon=1.3154 * u.deg, height=800 * u.m)
    start_dt = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    step_min = 5
    timeline = [start_dt + timedelta(minutes=m) for m in range(0, 24 * 60 + step_min, step_min)]
    times = Time(timeline, scale='utc')
    altaz = AltAz(obstime=times, location=location)

    def _iso_or_none(dt_obj):
        return dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ") if dt_obj else None

    def _crossing_time(vals, mode='rise'):
        # Interpolation linéaire simple autour de l'horizon (0°).
        for i in range(len(vals) - 1):
            a0, a1 = vals[i], vals[i + 1]
            if mode == 'rise' and a0 < 0 <= a1:
                frac = 0.0 if a1 == a0 else (0.0 - a0) / (a1 - a0)
                return timeline[i] + timedelta(seconds=frac * step_min * 60)
            if mode == 'set' and a0 > 0 >= a1:
                frac = 0.0 if a1 == a0 else (0.0 - a0) / (a1 - a0)
                return timeline[i] + timedelta(seconds=frac * step_min * 60)
        return None

    bodies = [
        ("Soleil", "sun", -26.74),
        ("Lune", "moon", -12.60),
        ("Jupiter", "jupiter", -2.70),
        ("Mars", "mars", 1.00),
        ("Saturne", "saturn", 0.70),
        ("Vénus", "venus", -4.20),
    ]

    results = []
    for label, body_name, mag in bodies:
        body_alt = get_body(body_name, times, location).transform_to(altaz).alt.deg.tolist()
        max_alt = max(body_alt)
        max_idx = body_alt.index(max_alt)
        rise_dt = _crossing_time(body_alt, mode='rise')
        set_dt = _crossing_time(body_alt, mode='set')
        transit_dt = timeline[max_idx]
        results.append(
            {
                "nom": label,
                "rise": _iso_or_none(rise_dt),
                "transit": _iso_or_none(transit_dt),
                "set": _iso_or_none(set_dt),
                "altitude_max": round(float(max_alt), 2),
                "magnitude": mag,
            }
        )

    return {
        "site": {
            "name": "Tlemcen",
            "lat": 34.8731,
            "lon": 1.3154,
            "altitude_m": 800,
        },
        "date_utc": start_dt.strftime("%Y-%m-%d"),
        "source": "astropy",
        "ephemerides": results,
    }


@app.route('/ephemerides')
def page_ephemerides():
    try:
        eph_payload = _compute_ephemerides_tlemcen_astropy()
    except Exception as e:
        log.warning("ephemerides astropy error: %s", e)
        eph_payload = {"error": str(e), "site": {"name": "Tlemcen"}}

    wants_json = request.args.get("format") == "json" or "application/json" in (request.headers.get("Accept") or "")
    if wants_json:
        return jsonify(eph_payload)
    return render_template('ephemerides.html', ephemerides_tlemcen=eph_payload)


@app.route('/sitemap.xml')
def sitemap_xml():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    base = "https://astroscan.space"
    urls = [
        ("/", "0.6", "monthly"),
        ("/portail", "1.0", "daily"),
        ("/ephemerides", "0.8", "daily"),
        ("/galerie", "0.8", "monthly"),
        ("/observatoire", "0.8", "daily"),
        ("/telescope", "0.8", "daily"),
        ("/ce-soir", "0.8", "daily"),
        ("/space-weather", "0.8", "daily"),
        ("/orbital-map", "0.8", "daily"),
        ("/a-propos", "0.6", "monthly"),
        ("/orbital-radio", "0.8", "daily"),
        ("/vision", "0.8", "daily"),
        ("/sondes", "0.8", "daily"),
    ]
    xml_items = [
        (
            "  <url>\n"
            f"    <loc>{base}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{prio}</priority>\n"
            "  </url>"
        )
        for path, prio, freq in urls
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(xml_items)
        + "\n</urlset>\n"
    )
    return Response(xml, mimetype='application/xml')


@app.route('/robots.txt')
def robots_txt():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'robots.txt', mimetype='text/plain')


@app.route('/europe-live')
def europe_live():
    return render_template('europe_live.html')


@app.route('/flight-radar')
def flight_radar():
    return render_template('flight_radar.html', lang=get_user_lang())


# ── PROXY CAMÉRAS — World Live ────────────────────────────────────────────────
# Caméras publiques mondiales, choisies pour stabilité et impact visuel.
# '__epic__' est une sentinelle : résout dynamiquement la dernière image NASA EPIC.
_CAM_SOURCES = {
    'matterhorn': [
        'https://zermatt.roundshot.com/zermatt.jpg',
        'https://www.zermatt.ch/var/zermatt/storage/images/media/webcam/matterhorn.jpg',
    ],
    'aurora': [
        'https://nordlysobservatoriet.no/allsky/latest_small.jpg',
        'https://arcticspace.no/allsky_images/latest.jpg',
    ],
    'canyon': [
        'https://www.nps.gov/grca/planyourvisit/webcam-images/south-rim.jpg',
        'https://grandcanyonsunrise.org/livecam/latest.jpg',
    ],
    'fuji': [
        'https://livecam.fujigoko.tv/cameras/fujigoko6.jpg',
        'https://n-img00.tsite.jp/webcam/fujigoko/live.jpg',
    ],
    'iss': [
        '__epic__',  # NASA EPIC — dernière image naturelle de la Terre (résolution dynamique)
        'https://eol.jsc.nasa.gov/DatabaseImages/ESC/small/ISS070/ISS070-E-75001.JPG',
    ],
}

_CAM_ALLOWED    = frozenset(_CAM_SOURCES)
_CAM_IMG_CACHE  = {}   # {city: {'ts': monotonic, 'data': bytes}}
_CAM_CACHE_TTL  = 30   # secondes — déduplique les rafraîchissements du frontend

# Un verrou par ville : les requêtes concurrentes ne s'empilent pas en workers bloqués.
_CAM_FETCH_LOCKS = {city: threading.Lock() for city in _CAM_SOURCES}

_CAM_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)
_CAM_FETCH_HEADERS = {
    'User-Agent':      _CAM_UA,
    'Accept':          'image/jpeg,image/*,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}

# Cache URL EPIC (1h TTL) — évite un appel API à chaque snapshot ISS.
_EPIC_URL_CACHE = {'url': None, 'ts': 0.0}
_EPIC_URL_TTL   = 3600


def _get_latest_epic_url():
    """Retourne l'URL JPEG de la dernière image naturelle DSCOVR/EPIC de la NASA."""
    now = time.monotonic()
    if _EPIC_URL_CACHE['url'] and (now - _EPIC_URL_CACHE['ts']) < _EPIC_URL_TTL:
        return _EPIC_URL_CACHE['url']
    r = requests.get(
        'https://epic.gsfc.nasa.gov/api/natural',
        timeout=(3, 8), headers={'User-Agent': _CAM_UA},
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise ValueError('EPIC API: aucune image disponible')
    img  = data[0]
    date = img['date'][:10].replace('-', '/')           # "yyyy/mm/dd"
    url  = f'https://epic.gsfc.nasa.gov/archive/natural/{date}/jpg/{img["image"]}.jpg'
    _EPIC_URL_CACHE['url'] = url
    _EPIC_URL_CACHE['ts']  = now
    log.info('[CAM EPIC] URL résolue : %s', url)
    return url


def _cam_resolve(raw_url):
    """Résout la sentinelle __epic__ en URL concrète ; passe les autres URLs telles quelles."""
    if raw_url == '__epic__':
        return _get_latest_epic_url()
    return raw_url


def _cam_fetch_url(url):
    """Télécharge un snapshot JPEG depuis url. Retourne les bytes. Lève sur erreur."""
    kw = dict(
        timeout=(5, 12), headers=_CAM_FETCH_HEADERS,
        allow_redirects=True, stream=False,
    )
    try:
        r = requests.get(url, verify=True, **kw)
    except requests.exceptions.SSLError:
        r = requests.get(url, verify=False, **kw)
    r.raise_for_status()
    data = r.content
    if not data:
        raise ValueError('réponse vide')
    ct = r.headers.get('content-type', '')
    if 'image' not in ct and data[:3] != b'\xff\xd8\xff':
        raise ValueError(f'pas une image : content-type={ct!r}')
    return data


def _cam_response(data):
    resp = Response(data, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma']        = 'no-cache'
    resp.headers['Expires']       = '0'
    return resp


@app.route('/proxy-cam/<city>.jpg')
def proxy_cam(city):
    if city not in _CAM_ALLOWED:
        abort(404)

    cached = _CAM_IMG_CACHE.get(city)
    now    = time.monotonic()

    # Cache frais → répondre immédiatement sans toucher le réseau
    if cached and (now - cached['ts']) < _CAM_CACHE_TTL:
        return _cam_response(cached['data'])

    # Verrou non-bloquant : autre thread déjà en fetch → cache périmé ou 503
    lock = _CAM_FETCH_LOCKS[city]
    if not lock.acquire(blocking=False):
        log.debug('[CAM SKIP] %s — fetch en cours, cache servi', city)
        if cached:
            return _cam_response(cached['data'])
        return Response('offline', status=503, mimetype='text/plain')

    try:
        # Re-vérifier après acquisition : autre thread peut avoir rafraîchi
        cached = _CAM_IMG_CACHE.get(city)
        if cached and (time.monotonic() - cached['ts']) < _CAM_CACHE_TTL:
            return _cam_response(cached['data'])

        for raw_url in _CAM_SOURCES[city]:
            try:
                url  = _cam_resolve(raw_url)
                data = _cam_fetch_url(url)
                _CAM_IMG_CACHE[city] = {'ts': time.monotonic(), 'data': data}
                log.info('[CAM OK] %s ← %s (%d B)', city, url, len(data))
                return _cam_response(data)
            except requests.HTTPError as exc:
                st = exc.response.status_code if exc.response is not None else '?'
                log.warning('[CAM FAIL] %s ← %s  HTTP %s', city, raw_url, st)
            except requests.RequestException as exc:
                log.warning('[CAM FAIL] %s ← %s  %s', city, raw_url, exc)
            except Exception as exc:
                log.warning('[CAM FAIL] %s ← %s  %s', city, raw_url, exc)

        # Toutes les sources échouées — cache périmé ou 503 (canvas front-end prend le relais)
        if cached:
            age = time.monotonic() - cached['ts']
            log.info('[CAM CACHE SERVED] %s (périmé, age=%.0fs)', city, age)
            return _cam_response(cached['data'])

        log.warning('[CAM OFFLINE] %s — toutes sources échouées, aucun cache', city)
        return Response('offline', status=503, mimetype='text/plain')

    finally:
        lock.release()


@app.route('/contact', methods=['POST'])
def contact_form():
    """Formulaire de contact — enregistre la soumission dans les logs."""
    import datetime as _dt
    allowed, _ = _api_rate_limit_allow(_client_ip_from_request(request), limit=5, window_sec=3600)
    if not allowed:
        return jsonify({"ok": False, "error": "Trop de soumissions. Réessayez dans une heure."}), 429
    try:
        data = request.get_json(silent=True) or request.form
        nom       = str(data.get('nom', '')).strip()[:120]
        organisme = str(data.get('organisme', '')).strip()[:200]
        message   = str(data.get('message', '')).strip()[:2000]
        if not nom or not message:
            return jsonify({"ok": False, "error": "Nom et message requis."}), 400
        ip = _client_ip_from_request(request)
        ts = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        log.info(
            "CONTACT_FORM | ts=%s | ip=%s | nom=%r | organisme=%r | message=%r",
            ts, ip, nom, organisme, message[:200]
        )
        contact_log_path = f"{STATION}/logs/contact_messages.log"
        try:
            with open(contact_log_path, 'a', encoding='utf-8') as f:
                f.write(f"---\nDate: {ts}\nIP: {ip}\nNom: {nom}\nOrganisme: {organisme}\nMessage:\n{message}\n\n")
        except Exception as _e:
            log.warning("contact log write error: %s", _e)
        return jsonify({"ok": True, "message": "Message reçu. Nous vous répondrons dans les meilleurs délais."})
    except Exception as e:
        log.error("contact_form error: %s", e)
        return jsonify({"ok": False, "error": "Erreur serveur."}), 500


# Proxy avions OpenSky → AirLabs (cache 30 s + compteur requêtes AirLabs).
_flights_cache = {"data": None, "ts": 0.0, "airlabs_count": 0}


@app.route("/api/flights")
def api_flights():
    """OpenSky prioritaire ; AirLabs secours ; cache 30 s ; compteur AirLabs ; repli stale."""
    import os
    import requests as req

    global _flights_cache

    now = time.time()
    if _flights_cache.get("data") is not None and (now - float(_flights_cache.get("ts") or 0.0)) < 30:
        return jsonify(_flights_cache["data"])

    OPENSKY_USER = (os.environ.get("OPENSKY_USER") or "").strip()
    OPENSKY_PASS = (os.environ.get("OPENSKY_PASS") or "").strip()
    AIRLABS_KEY = (os.environ.get("AIRLABS_KEY") or "").strip()

    # --- Source 1 : OpenSky ---
    try:
        auth = (OPENSKY_USER, OPENSKY_PASS) if OPENSKY_USER else None
        r = req.get(
            "https://opensky-network.org/api/states/all",
            timeout=12,
            auth=auth,
            headers={"User-Agent": "AstroScan/2.0"},
        )
        if r.status_code == 200:
            data = r.json()
            states = []
            for s in data.get("states") or []:
                if not s or len(s) < 11:
                    continue
                if s[5] is None or s[6] is None:
                    continue
                states.append(
                    {
                        "callsign": (s[1] or "").strip(),
                        "origin": s[2] or "??",
                        "lon": s[5],
                        "lat": s[6],
                        "alt": round(s[7] or 0),
                        "speed": round((s[9] or 0) * 3.6),
                        "heading": round(s[10] or 0),
                        "on_ground": s[8],
                    }
                )
            result = {
                "states": states,
                "time": data.get("time"),
                "count": len(states),
                "source": "opensky",
                "airlabs_used": int(_flights_cache.get("airlabs_count") or 0),
            }
            _flights_cache.update({"data": result, "ts": now})
            return jsonify(result)
    except Exception:
        pass

    # --- Source 2 : AirLabs (clé en query param ; pas d'interpolation dans les logs serveur) ---
    if AIRLABS_KEY:
        try:
            r = req.get(
                "https://airlabs.co/api/v9/flights",
                params={"api_key": AIRLABS_KEY},
                timeout=12,
                headers={"User-Agent": "AstroScan/2.0"},
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("error"):
                    raise ValueError(data["error"])
                flights = data.get("response") or []
                if not isinstance(flights, list):
                    flights = []
                states = []
                for f in flights:
                    if not isinstance(f, dict):
                        continue
                    if not (f.get("lat") and f.get("lng")):
                        continue
                    states.append(
                        {
                            "callsign": f.get("flight_iata") or f.get("flight_icao") or "???",
                            "origin": f.get("flag") or f.get("dep_iata") or "??",
                            "lon": f.get("lng"),
                            "lat": f.get("lat"),
                            "alt": round((f.get("alt") or 0) * 0.3048),
                            "speed": round((f.get("speed") or 0) * 1.852),
                            "heading": round(f.get("dir") or 0),
                            "on_ground": False,
                        }
                    )
                _flights_cache["airlabs_count"] = int(_flights_cache.get("airlabs_count") or 0) + 1
                result = {
                    "states": states,
                    "time": int(now),
                    "count": len(states),
                    "source": "airlabs",
                    "airlabs_used": int(_flights_cache["airlabs_count"]),
                }
                _flights_cache.update({"data": result, "ts": now})
                return jsonify(result)
        except Exception:
            pass

    if _flights_cache.get("data"):
        old = dict(_flights_cache["data"])
        old["stale"] = True
        return jsonify(old)

    return jsonify(
        {
            "states": [],
            "count": 0,
            "error": "all_sources_failed",
            "airlabs_used": int(_flights_cache.get("airlabs_count") or 0),
        }
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
