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

from app.blueprints.analytics import bp as analytics_bp
app.register_blueprint(analytics_bp)

# Blueprint export — added PASS 4 (ephemerides, apod-history, existing CSV/JSON)
from app.blueprints.export import bp as export_bp
app.register_blueprint(export_bp)

# Blueprint cameras — added PASS 6 (sky-camera, observatory status, skyview, telescope_live img, audio-proxy)
from app.blueprints.cameras import bp as cameras_bp
app.register_blueprint(cameras_bp)

# Blueprint archive — added PASS 6 (archive CRUD, classification, MAST, shield, microobservatory static)
from app.blueprints.archive import bp as archive_bp
app.register_blueprint(archive_bp)

# Blueprint weather — added PASS 7 (météo terrestre + spatiale + aurores + space-weather)
from app.blueprints.weather import bp as weather_bp
app.register_blueprint(weather_bp)

# Blueprint astro — added PASS 7 (éphémérides, lune, tonight, astro/object)
from app.blueprints.astro import bp as astro_bp
app.register_blueprint(astro_bp)

# Blueprint feeds — added PASS 8 (NASA, NOAA SWPC, JPL, live feeds, alerts)
from app.blueprints.feeds import bp as feeds_bp
app.register_blueprint(feeds_bp)

# Blueprint telescope — added PASS 9 (Skyview, mission control, telescope hub, image/title, hubble)
from app.blueprints.telescope import bp as telescope_bp
app.register_blueprint(telescope_bp)

# Blueprint ai — added PASS 10 (AEGIS chat, Claude/Gemini/Groq, telescope/live, jwst, translate, explain)
from app.blueprints.ai import bp as ai_bp
app.register_blueprint(ai_bp)

# Blueprint lab — added PASS 13 (Digital Lab + Space Analysis Engine)
from app.blueprints.lab import bp as lab_bp
app.register_blueprint(lab_bp)

# Blueprint research — added PASS 13 (Research Center + Science + Space Intelligence)
from app.blueprints.research import bp as research_bp
app.register_blueprint(research_bp)

# Blueprint satellites — added PASS 14 (TLE catalog + per-satellite SGP4 + passes)
from app.blueprints.satellites import bp as satellites_bp
app.register_blueprint(satellites_bp)


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
# MIGRATED TO export_bp PASS 4 — see app/blueprints/export/__init__.py
# @app.route("/api/export/visitors.csv")
# @app.route("/api/export/visitors.json")
# @app.route("/api/export/ephemerides.json")
# @app.route("/api/export/observations.json")
# @app.route("/api/export/apod-history.json")

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









# MIGRATED TO system_bp PASS 4 — see app/blueprints/system/__init__.py
# @app.route('/health', methods=['GET'])          → health_check()
# @app.route('/selftest', methods=['GET'])         → selftest()
# @app.route('/api/tle/refresh', methods=['POST']) → api_tle_refresh()


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


# MIGRATED TO pages_bp PASS 5 — /overlord_live → see app/blueprints/pages/__init__.py (overlord_live)
# MIGRATED TO pages_bp PASS 5 — /galerie → see app/blueprints/pages/__init__.py (galerie)
# MIGRATED TO pages_bp PASS 5 — /observatoire → see app/blueprints/pages/__init__.py (observatoire)

# MIGRATED TO pages_bp 2026-05-02 (B-RECYCLE R2) — see app/blueprints/pages/__init__.py
# @app.route('/vision')
# def vision():
#     return render_template('vision.html')


# MIGRATED TO pages_bp PASS 5 — /vision-2026 → see app/blueprints/pages/__init__.py (vision_2026)
# MIGRATED TO pages_bp PASS 5 — /sondes → see app/blueprints/pages/__init__.py (sondes)
# MIGRATED TO pages_bp PASS 5 — /telemetrie-sondes → see app/blueprints/pages/__init__.py (telemetrie_sondes)


# MIGRATED TO cameras_bp PASS 6 — /sky-camera → see app/blueprints/cameras/__init__.py (sky_camera)
# MIGRATED TO cameras_bp PASS 6 — /api/sky-camera/analyze → see app/blueprints/cameras/__init__.py (api_sky_camera_analyze)


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


# MIGRATED TO feeds_bp PASS 11 — /api/sondes/live → see app/blueprints/feeds/__init__.py (api_sondes_live)




# MIGRATED TO pages_bp 2026-05-02 (B-RECYCLE R2) — see app/blueprints/pages/__init__.py
# @app.route('/scientific')
# def scientific():
#     return render_template('scientific.html')

# ══════════════════════════════════════════════════════════════
# API — DONNÉES PRINCIPALES
# ══════════════════════════════════════════════════════════════

# @app.route('/api/latest')
# def api_latest():
#     lang = request.args.get('lang', 'fr').lower()
#     try:
#         conn = get_db()
#         cur  = conn.cursor()
#         total     = cur.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
#         anomalies = cur.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
#         sources   = cur.execute("SELECT COUNT(DISTINCT source) FROM observations").fetchone()[0]
#         try:
#             req_j = cur.execute(
#                 "SELECT COUNT(*) FROM observations WHERE date(timestamp)=date('now')"
#             ).fetchone()[0]
#         except:
#             req_j = 0
# 
#         try:
#             limit_arg = request.args.get('limit', '20')
#             limit = min(200, max(1, int(limit_arg))) if str(limit_arg).isdigit() else 20
#         except Exception:
#             limit = 20
# 
#         try:
#             rows = cur.execute(
#                 "SELECT id, timestamp, source, analyse_gemini, analyse_gemini as rapport_gemini, "
#                 "COALESCE(rapport_fr,'') as rapport_fr, objets_detectes, anomalie, "
#                 "COALESCE(title,'') as title, COALESCE(objets_detectes,'') as type_objet, "
#                 "COALESCE(score_confiance,0.0) as confidence "
#                 "FROM observations ORDER BY id DESC LIMIT ?", (limit,)
#             ).fetchall()
#         except Exception:
#             rows = cur.execute(
#                 "SELECT id, timestamp, source, analyse_gemini, analyse_gemini as rapport_gemini, "
#                 "'' as rapport_fr, objets_detectes, anomalie, "
#                 "'' as title, '' as type_objet, 0.0 as confidence "
#                 "FROM observations ORDER BY id DESC LIMIT ?", (limit,)
#             ).fetchall()
#         conn.close()
# 
#         obs_list = []
#         for row in rows:
#             r = dict(row)
#             raw = r.get('rapport_gemini') or r.get('analyse_gemini') or ''
#             if lang == 'fr':
#                 fr = (r.get('rapport_fr') or '').strip()
#                 r['rapport_gemini'] = fr if fr else raw
#             else:
#                 r['rapport_gemini'] = raw
#             r['rapport_display'] = r['rapport_gemini']
#             obs_list.append(r)
# 
#         return jsonify({
#             'ok': True, 'total': total, 'anomalies': anomalies,
#             'sources': sources, 'telescopes': 9, 'req_jour': req_j,
#             'observations': obs_list,
#             'notice': 'Analyses AEGIS',
#         })
#     except Exception as e:
#         log.error(f"api_latest: {e}")
#         return jsonify({'ok': False, 'error': str(e), 'total': 0, 'observations': []})
# 
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






# @app.route('/api/accuracy/export.csv')
# def api_accuracy_export_csv():
#     rows = get_accuracy_history()
#     lines = ["ts,distance_km"]
#     for row in rows:
#         ts = row.get("ts", "")
#         distance = row.get("distance_km", "")
#         lines.append(f"{ts},{distance}")
#     csv_payload = "\n".join(lines) + "\n"
#     return Response(
#         csv_payload,
#         mimetype="text/csv",
#         headers={
#             "Content-Disposition": 'attachment; filename="accuracy_history.csv"'
#         },
#     )
# 

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


# MIGRATED TO pages_bp PASS 5 — /ce_soir → see app/blueprints/pages/__init__.py (ce_soir_page)


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


# MIGRATED TO cameras_bp PASS 6 — /visiteurs-live → see app/blueprints/cameras/__init__.py (visiteurs_live_page)
# MIGRATED TO cameras_bp PASS 6 — /api/audio-proxy → see app/blueprints/cameras/__init__.py (api_audio_proxy)


# ══════════════════════════════════════════════════════════════
# GUIDE TOURISTIQUE STELLAIRE (Claude + éphémérides)
# ══════════════════════════════════════════════════════════════

# MIGRATED TO ai_bp PASS 10 — /guide-stellaire → see app/blueprints/ai/__init__.py (guide_stellaire_page)
# MIGRATED TO ai_bp PASS 10 — /oracle-cosmique → see app/blueprints/ai/__init__.py (oracle_cosmique_page)


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


# MIGRATED TO ai_bp PASS 10 — /api/guide-geocode → see app/blueprints/ai/__init__.py (api_guide_geocode)


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


# MIGRATED TO weather_bp PASS 7 — /aurores → see app/blueprints/weather/__init__.py (aurores_page)
# MIGRATED TO weather_bp PASS 7 — /api/aurore → see app/blueprints/weather/__init__.py (api_aurore)


# MIGRATED TO weather_bp PASS 7 — /api/weather → see app/blueprints/weather/__init__.py (api_weather_alias)
# MIGRATED TO weather_bp PASS 7 — /api/weather/local → see app/blueprints/weather/__init__.py (api_weather_local)


# MIGRATED TO weather_bp PASS 7 — /api/weather/bulletins → see app/blueprints/weather/__init__.py (api_weather_bulletins)
# MIGRATED TO weather_bp PASS 7 — /api/weather/bulletins/latest → see app/blueprints/weather/__init__.py (api_weather_bulletins_latest)
# MIGRATED TO weather_bp PASS 7 — /api/weather/history → see app/blueprints/weather/__init__.py (api_weather_history)
# MIGRATED TO weather_bp PASS 7 — /api/weather/bulletins/save → see app/blueprints/weather/__init__.py (api_weather_bulletins_save)


# MIGRATED TO feeds_bp PASS 14 — /api/apod alias → see app/blueprints/feeds/__init__.py (api_apod_alias)


@app.route("/api/oracle", methods=["POST"])
def api_oracle_alias():
    try:
        return api_oracle_cosmique()
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


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


# MIGRATED TO telescope_bp PASS 9 — /api/telescope/nightly → see app/blueprints/telescope/__init__.py (api_telescope_nightly)


@app.route('/api/telescope/trigger-nightly', methods=['POST'])
def api_telescope_trigger_nightly():
    """Déclenche manuellement le pipeline nocturne Harvard MO."""
    import threading
    t = threading.Thread(target=_telescope_nightly_tlemcen, daemon=True)
    t.start()
    return jsonify({'ok': True, 'message': 'Pipeline nocturne démarré en arrière-plan'})


# MIGRATED TO cameras_bp PASS 6 — /telescope_live/<path:filename> → see app/blueprints/cameras/__init__.py (serve_telescope_live_img)


# MIGRATED TO telescope_bp PASS 9 — /mission-control → see app/blueprints/telescope/__init__.py (mission_control)
# MIGRATED TO telescope_bp PASS 9 — /api/mission-control → see app/blueprints/telescope/__init__.py (api_mission_control)


# MIGRATED TO astro_bp PASS 7 — /api/astro/object → see app/blueprints/astro/__init__.py (api_astro_object)

# MIGRATED TO feeds_bp PASS 8 — /api/news → see app/blueprints/feeds/__init__.py (api_news)

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

# ── Health check ──
# @app.route('/api/health')
# def api_health():
#     total, anom, sources = 0, 0, []
#     uptime_str = '—'
#     try:
#         conn = sqlite3.connect('/root/astro_scan/data/archive_stellaire.db', timeout=10.0)
#         total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
#         anom  = conn.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
#         rows  = conn.execute("SELECT DISTINCT source FROM observations WHERE timestamp > datetime('now','-7 days')").fetchall()
#         sources = [r[0] for r in rows]
#         last  = conn.execute("SELECT COALESCE(title,objets_detectes,'') as t, timestamp FROM observations ORDER BY id DESC LIMIT 1").fetchone()
#         conn.close()
#     except: pass
#     try:
#         uptime_str = open('/proc/uptime').read().split()[0]
#         s = int(float(uptime_str))
#         uptime_str = f"{s//3600}h {(s%3600)//60}m"
#     except: pass
#     import os
#     payload = {
#         'ok': True, 'station': 'ORBITAL-CHOHRA',
#         'ip': '5.78.153.17', 'location': 'Tlemcen, Algérie',
#         'director': 'Zakaria Chohra — Tlemcen, Algérie',
#         'time_utc': datetime.now(timezone.utc).isoformat(),
#         'uptime': uptime_str,
#         'db': {'total': total, 'anomalies': anom, 'sources': sources},
#         'services': {
#             'gemini': 'active' if os.environ.get('GEMINI_API_KEY') else 'missing',
#             'grok':   'inactive',
#             'groq':   'active' if os.environ.get('GROQ_API_KEY')   else 'missing',
#             'nasa':   'active' if os.environ.get('NASA_API_KEY')    else 'missing',
#             'aegis': 'active', 'sdr': 'active', 'iss': 'active'
#         },
#         'coordinates': {'lat': 34.87, 'lon': 1.32, 'alt_m': 800, 'timezone': 'Africa/Algiers'}
#     }
#     # Champs opérationnels additifs (monitoring / V2) — ne modifient pas les clés historiques ci-dessus
#     try:
#         if _core_status_engine is not None:
#             payload['operational'] = _core_status_engine.build_operational_health(
#                 STATION,
#                 DB_PATH,
#                 TLE_CACHE,
#                 TLE_CACHE_FILE,
#                 ws_present=True,
#                 sse_present=True,
#             )
#             payload['data_credibility'] = _core_status_engine.data_credibility_stub(TLE_CACHE, TLE_CACHE_FILE)
#     except Exception as ex:
#         log.debug("api_health operational: %s", ex)
#         try:
#             payload['operational'] = {'status': 'unknown', 'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'error': 'probe_partial'}
#         except Exception:
#             pass
#     return jsonify(payload)
# 



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


# @app.route('/status')
# def api_status():
#     """
#     GET /status
#     Snapshot JSON stable pour badges UI / monitoring (pas d'appels réseau bloquants).
#     """
#     return jsonify(build_status_snapshot_dict())
# 

# @app.route("/stream/status")
# def stream_status_sse():
#     """
#     Flux SSE additif : même snapshot que /status, toutes les ~3 s.
#     Alternative stable au WebSocket pour Gunicorn multi-workers (pas de retrait de /ws/status).
#     """
#     def _gen():
#         while True:
#             try:
#                 snap = build_status_snapshot_dict()
#                 yield "data: " + json.dumps(snap, default=str) + "\n\n"
#             except Exception as ex:
#                 try:
#                     yield "data: " + json.dumps({"error": str(ex)[:200], "stream": "status"}) + "\n\n"
#                 except Exception:
#                     pass
#             time.sleep(3)
# 
#     return Response(
#         stream_with_context(_gen()),
#         mimetype="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "X-Accel-Buffering": "no",
#         },
#     )
# 

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


# MIGRATED TO telescope_bp PASS 9 — /api/hubble/images → see app/blueprints/telescope/__init__.py (api_hubble_images)


# MIGRATED TO feeds_bp PASS 8 — /api/mars/weather → see app/blueprints/feeds/__init__.py (api_mars_weather)


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


# MIGRATED TO ai_bp PASS 10 — /api/jwst/images → see app/blueprints/ai/__init__.py (api_jwst_images)
# MIGRATED TO ai_bp PASS 10 — /api/jwst/refresh → see app/blueprints/ai/__init__.py (api_jwst_refresh)
# (différés PASS 8/9 levés : helpers _fetch_jwst_live_images + _JWST_STATIC déplacés vers
#  app/services/observatory_feeds.py)


# MIGRATED TO feeds_bp PASS 8 — /api/neo → see app/blueprints/feeds/__init__.py (api_neo)
# MIGRATED TO feeds_bp PASS 8 — /api/nasa/apod → see app/blueprints/feeds/__init__.py (api_nasa_apod)


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


# MIGRATED TO satellites_bp PASS 14 — /api/satellites/tle → see app/blueprints/satellites/__init__.py (api_satellites_tle)
# MIGRATED TO satellites_bp PASS 14 — /api/satellites/tle/debug → see app/blueprints/satellites/__init__.py (debug_tle)




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

# MIGRATED TO iss_bp 2026-05-02 (B3b) — see app/blueprints/iss/routes.py
# @app.route('/orbital-map')
# def orbital_map_page():
#     return render_template('orbital_map.html', cesium_token=CESIUM_TOKEN)


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


# MIGRATED TO main_bp 2026-05-02 (B-RECYCLE R3) — see app/blueprints/main/__init__.py
# @app.route('/about')
# @app.route('/a-propos')
# def about():
#     return render_template('a_propos.html')


# ═══ TÉLESCOPE NASA SKYVIEW ═══════════════════════════════════
from skyview import OBJETS_TLEMCEN, SURVEYS, get_object_image, get_image_url as skyview_get_image_url

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
import sqlite3 as _sqlite3

def _get_db_visitors():
    return _sqlite3.connect("/root/astro_scan/data/archive_stellaire.db")


# MIGRATED TO analytics_bp PASS 12 — /api/visitors/globe-data → see app/blueprints/analytics/__init__.py (api_visitors_globe_data)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/stream → see app/blueprints/analytics/__init__.py (api_visitors_stream)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/log POST → see app/blueprints/analytics/__init__.py (api_log_visitor)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/geo → see app/blueprints/analytics/__init__.py (api_visitors_geo)
# MIGRATED TO analytics_bp PASS 12 — /api/visitors/stats → see app/blueprints/analytics/__init__.py (api_visitors_stats)




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
