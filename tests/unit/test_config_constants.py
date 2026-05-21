"""Unit tests — services.config (constantes pures, validations sanity)."""
from __future__ import annotations

import pytest

from services import config as cfg


pytestmark = pytest.mark.unit


# ── HTTP timeouts ─────────────────────────────────────────────────────────────


def test_req_default_timeout_positive():
    assert cfg.REQ_DEFAULT_TIMEOUT > 0
    assert cfg.REQ_DEFAULT_TIMEOUT <= 60


def test_slow_ms_thresholds_ordered():
    assert cfg.REQ_SLOW_MS < cfg.REQ_VERY_SLOW_MS


# ── Stale thresholds ─────────────────────────────────────────────────────────


def test_stale_threshold_in_realistic_range():
    assert 3600 <= cfg.STALE_DATA_THRESHOLD_SEC <= 7 * 86400


def test_aging_smaller_than_stale():
    assert cfg.AGING_DATA_THRESHOLD_SEC < cfg.STALE_DATA_THRESHOLD_SEC


# ── TLE config ───────────────────────────────────────────────────────────────


def test_tle_urls_https():
    assert cfg.TLE_SOURCE_URL.startswith("https://")


def test_tle_refresh_positive():
    assert cfg.TLE_DEFAULT_REFRESH_SECONDS > 0


def test_tle_backoff_cap_above_base():
    assert cfg.TLE_BACKOFF_EXP_CAP_SEC >= cfg.TLE_BACKOFF_BASE_SEC


def test_tle_cooldown_window_ordered():
    assert cfg.TLE_COOLDOWN_MIN_SEC <= cfg.TLE_COOLDOWN_MAX_SEC


# ── Cache TTLs all positive ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "TTL_IMAGE_CACHE", "TTL_JWST", "TTL_APOD", "TTL_NEO", "TTL_NASA_SOLAR",
        "TTL_ASTEROIDS", "TTL_SOLAR_WEATHER", "TTL_SPACEX", "TTL_SPACE_NEWS",
        "TTL_MARS_WEATHER", "TTL_ISS_PASSES", "TTL_VOYAGER", "TTL_PLANETS_V1",
        "TTL_EPH_TLEMCEN",
    ],
)
def test_ttl_positive(name):
    val = getattr(cfg, name)
    assert isinstance(val, int)
    assert val > 0
    assert val <= 7 * 86400


# ── URLs externes ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "NASA_APOD_URL", "NASA_NEO_URL", "NASA_DONKI_URL",
        "NOAA_KP_URL", "NOAA_ALERTS_URL",
        "ISS_WHERETHEISS_URL",
        "CELESTRAK_GP_URL", "SATNOGS_TLE_URL",
        "OPEN_METEO_URL",
        "MO_DIR_URL", "MO_DL_BASE",
    ],
)
def test_external_urls_https(name):
    url = getattr(cfg, name)
    assert isinstance(url, str)
    assert url.startswith("https://")


def test_iss_crew_url_http_allowed():
    # open-notify is http-only legacy
    assert cfg.ISS_CREW_URL.startswith(("http://", "https://"))


# ── Rate limits ──────────────────────────────────────────────────────────────


def test_rate_limit_contact_positive():
    assert cfg.RATE_LIMIT_CONTACT_PER_HOUR > 0


def test_rate_limit_translate_positive():
    assert cfg.RATE_LIMIT_TRANSLATE_PER_MIN > 0


# ── SQLite ───────────────────────────────────────────────────────────────────


def test_sqlite_timeout_seconds():
    assert cfg.SQLITE_TIMEOUT > 0


def test_sqlite_busy_timeout_ms_positive():
    assert cfg.SQLITE_BUSY_TIMEOUT > 0


def test_sqlite_cache_size_kb_negative():
    """SQLite PRAGMA: negative cache_size = kilobytes."""
    assert cfg.SQLITE_CACHE_SIZE < 0
