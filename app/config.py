"""
app.config — Constantes de configuration centralisées AstroScan.

Toutes les constantes en MAJUSCULES extraites de station_web.py,
organisées par domaine fonctionnel. Les Blueprints importent ici
plutôt que depuis station_web.

Usage :
    from app.config import SEO_HOME_TITLE, SEO_HOME_DESCRIPTION, STATION
    from app.config import TLE_SOURCE_URL, TLE_DEFAULT_REFRESH_SECONDS
    from app.config import DB_PATH, WEATHER_DB_PATH
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Chemins — répertoire racine et bases de données
# ---------------------------------------------------------------------------

STATION: str = os.environ.get("STATION", "/root/astro_scan")

# Bases SQLite principales
DB_PATH: str             = f"{STATION}/data/archive_stellaire.db"
WEATHER_DB_PATH: str     = os.path.join(STATION, "weather_bulletins.db")
WEATHER_HISTORY_DIR: str = f"{STATION}/data/weather_history"
WEATHER_ARCHIVE_DIR: str = f"{STATION}/data/weather_archive"

# Fichiers temps-réel télescope
IMG_PATH: str   = f"{STATION}/telescope_live/current_live.jpg"
TITLE_F: str    = f"{STATION}/telescope_live/current_title.txt"
REPORT_F: str   = f"{STATION}/telescope_live/live_report.txt"
SHIELD_F: str   = f"{STATION}/data/shield_status.json"
HUB_F: str      = f"{STATION}/data/telescope_hub.json"
SDR_F: str      = f"{STATION}/data/sdr_status.json"

# ISS passages pré-calculés
PASSAGES_ISS_JSON: str    = f"{STATION}/static/passages_iss.json"
CALC_PASSAGES_SCRIPT: str = os.path.join(STATION, "calculateur_passages.py")

# TLE cache disque
TLE_CACHE_FILE: str    = f"{STATION}/data/tle_active_cache.json"
TLE_LOCAL_FALLBACK: str = f"{STATION}/data/tle/active.tle"

# ---------------------------------------------------------------------------
# SEO — titre et description canoniques (accueil, landing, og/twitter)
# ---------------------------------------------------------------------------

SEO_HOME_TITLE: str = "AstroScan-Chohra"

SEO_HOME_DESCRIPTION: str = (
    "AstroScan-Chohra est une plateforme avancée d'analyse et de surveillance spatiale en temps réel. "
    "Suivez les satellites, les missions spatiales et les phénomènes astronomiques."
)

# ---------------------------------------------------------------------------
# TLE — source, refresh, backoff
# ---------------------------------------------------------------------------

TLE_SOURCE_URL: str = "https://db.satnogs.org/api/tle/?format=json&satellite__status=alive"

TLE_DEFAULT_REFRESH_SECONDS: int = 900          # 15 min
TLE_REFRESH_SECONDS: int         = 900          # alias legacy
TLE_BACKOFF_REFRESH_SECONDS: int = 6 * 3600     # 6 h (legacy, non utilisé en runtime)

TLE_BACKOFF_BASE_SEC: int   = 30
TLE_BACKOFF_EXP_CAP_SEC: int = 120

TLE_COOLDOWN_AFTER_FAILURES: int = 3
TLE_COOLDOWN_MIN_SEC: int        = 60
TLE_COOLDOWN_MAX_SEC: int        = 120

# ---------------------------------------------------------------------------
# Cache — TTL en secondes
# ---------------------------------------------------------------------------

MAX_CACHE_SIZE: int          = 500
TRANSLATE_TTL_SECONDS: int   = 3600    # 1 h
STALE_DATA_THRESHOLD_SEC: int = 86400  # 24 h — donnée considérée périmée
AGING_DATA_THRESHOLD_SEC: int = 43200  # 12 h — donnée considérée ancienne

# ---------------------------------------------------------------------------
# Requêtes HTTP sortantes — timeouts
# ---------------------------------------------------------------------------

REQ_DEFAULT_TIMEOUT: int  = 10     # secondes
REQ_SLOW_MS: int          = 1500   # seuil log "lente"
REQ_VERY_SLOW_MS: int     = 5000   # seuil log "très lente"

# ---------------------------------------------------------------------------
# AI / LLM — limites d'appels par session (reset au restart)
# ---------------------------------------------------------------------------

CLAUDE_MAX_CALLS: int = 100

# ---------------------------------------------------------------------------
# Coordonnées station Tlemcen (utilisées dans les calculs orbitaux)
# ---------------------------------------------------------------------------

from app.constants.observatory import (
    OBSERVER_LAT as _OBS_LAT,
    OBSERVER_LON as _OBS_LON,
    OBSERVER_ALT_M as _OBS_ALT,
)

TLEMCEN_LAT: float = _OBS_LAT       # 34.8753 °N
TLEMCEN_LON: float = _OBS_LON       # -1.3167 °W (NÉGATIF — OUEST Greenwich)
TLEMCEN_ALT: float = float(_OBS_ALT)  # 816 m

# ---------------------------------------------------------------------------
# Tokens / API Keys — lus depuis l'environnement
# Ne jamais hardcoder de clés ici.
# ---------------------------------------------------------------------------

CESIUM_TOKEN: str          = os.getenv("CESIUM_TOKEN", "")
NASA_API_KEY: str          = os.environ.get("NASA_API_KEY", "DEMO_KEY") or "DEMO_KEY"
ANTHROPIC_API_KEY: str     = os.environ.get("ANTHROPIC_API_KEY", "")
GROQ_API_KEY: str          = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY: str        = os.environ.get("GEMINI_API_KEY", "")
XAI_API_KEY: str           = os.environ.get("XAI_API_KEY", "")
SENTRY_DSN: str            = os.environ.get("SENTRY_DSN", "")

ASTROSCAN_OWNER_IPS: list[str] = [
    x.strip()
    for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(",")
    if x.strip()
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

SUPPORTED_LANGS: frozenset[str] = frozenset({"fr", "en"})
DEFAULT_LANG: str = "fr"
