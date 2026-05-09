"""Constantes centralisées AstroScan — URLs, timeouts, TTLs, seuils.

Source de vérité unique extraite de station_web.py.
Toutes valeurs pures (pas de dépendances Flask ni objets runtime).
"""

# ── HTTP / requests ───────────────────────────────────────────────────────────
REQ_DEFAULT_TIMEOUT = 10       # secondes, appliqué sur chaque requests.get/post
REQ_SLOW_MS         = 1500     # log si requête > 1.5 s
REQ_VERY_SLOW_MS    = 5000     # log critique si > 5 s

# ── Seuils fraîcheur données ──────────────────────────────────────────────────
STALE_DATA_THRESHOLD_SEC = 86400   # 24 h — données considérées périmées
AGING_DATA_THRESHOLD_SEC = 43200   # 12 h — données vieillissantes

# ── TLE (Two-Line Elements) ───────────────────────────────────────────────────
TLE_SOURCE_URL              = "https://db.satnogs.org/api/tle/?format=json&satellite__status=alive"
TLE_DEFAULT_REFRESH_SECONDS = 900        # 15 min
TLE_BACKOFF_BASE_SEC        = 30
TLE_BACKOFF_EXP_CAP_SEC     = 120
TLE_COOLDOWN_MIN_SEC        = 60
TLE_COOLDOWN_MAX_SEC        = 120

# ── Cache TTLs (secondes) ─────────────────────────────────────────────────────
TTL_IMAGE_CACHE   = 300        # 5 min — APOD / Hubble / archive (changent peu)
TTL_JWST          = 21600      # 6 h
TTL_APOD          = 1800       # 30 min
TTL_NEO           = 900        # 15 min
TTL_NASA_SOLAR    = 600        # 10 min
TTL_ASTEROIDS     = 3600       # 1 h
TTL_SOLAR_WEATHER = 300        # 5 min
TTL_SPACEX        = 3600       # 1 h
TTL_SPACE_NEWS    = 1800       # 30 min
TTL_MARS_WEATHER  = 3600       # 1 h
TTL_ISS_PASSES    = 600        # 10 min
TTL_VOYAGER       = 3600       # 1 h
TTL_PLANETS_V1    = 600        # 10 min
TTL_EPH_TLEMCEN   = 300        # 5 min — éphémérides Tlemcen

# ── URLs APIs externes ────────────────────────────────────────────────────────

# NASA
NASA_APOD_URL   = "https://api.nasa.gov/planetary/apod"
NASA_NEO_URL    = "https://api.nasa.gov/neo/rest/v1/feed"
NASA_DONKI_URL  = "https://api.nasa.gov/DONKI/notifications"

# NOAA / météo spatiale
NOAA_KP_URL     = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
NOAA_ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"

# ISS
ISS_WHERETHEISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
ISS_CREW_URL        = "http://api.open-notify.org/astros.json"

# CelesTrak
CELESTRAK_GP_URL    = "https://celestrak.org/SOCRATES/query.php?format=json"
SATNOGS_TLE_URL     = "https://db.satnogs.org/api/tle/?format=json&satellite__status=alive"

# Meteo
OPEN_METEO_URL      = "https://api.open-meteo.com/v1/forecast"

# MicroObservatory
MO_DIR_URL  = "https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/ImageDirectory.php"
MO_DL_BASE  = "https://mo-www.cfa.harvard.edu/ImageDirectory/"

# ── Limites rate-limiting ─────────────────────────────────────────────────────
RATE_LIMIT_CONTACT_PER_HOUR = 5
RATE_LIMIT_TRANSLATE_PER_MIN = 10

# ── SQLite ────────────────────────────────────────────────────────────────────
SQLITE_TIMEOUT       = 30      # secondes — connexion bloquante max
SQLITE_BUSY_TIMEOUT  = 5000    # ms — PRAGMA busy_timeout
SQLITE_CACHE_SIZE    = -32000  # kB négatif = 32 Mo par connexion
