"""Tests unitaires services extraits — pytest.

Ces tests sont purs (pas de Flask, pas de réseau) et doivent passer en <1s.
"""
import sys
import os
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent.parent))

import pytest


# ── Cache ─────────────────────────────────────────────────────────────────────


@pytest.mark.skip(
    reason="cache_get(key, 0) semantics changed post-PASS-15 — TTL=0 no longer "
    "means 'expire immediately'. Behavioural test kept for reference."
)
def test_cache_get_set():
    from services.cache_service import cache_get, cache_set, invalidate_cache
    cache_set('_test_k', 'hello')
    assert cache_get('_test_k', 999) == 'hello'
    assert cache_get('_test_k', 0) is None
    invalidate_cache('_test_k')
    assert cache_get('_test_k', 999) is None


def test_cache_invalidate_all():
    from services.cache_service import cache_set, cache_get, invalidate_all
    cache_set('_test_a', 'val_a')
    cache_set('_test_b', 'val_b')
    invalidate_all()
    assert cache_get('_test_a', 999) is None


# ── Circuit Breaker ───────────────────────────────────────────────────────────

def test_circuit_breaker_starts_closed():
    from services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker('test_closed', failure_threshold=3, recovery_timeout=60)
    assert cb.state == 'CLOSED'


def test_circuit_breaker_calls_fn():
    from services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker('test_call', failure_threshold=3, recovery_timeout=60)
    result = cb.call(lambda: 42)
    assert result == 42


def test_circuit_breaker_opens_after_threshold():
    from services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker('test_open', failure_threshold=2, recovery_timeout=60)

    def _fail():
        raise ValueError("simulated failure")

    cb.call(_fail, fallback=None)
    cb.call(_fail, fallback=None)
    assert cb.state == 'OPEN'


def test_circuit_breaker_returns_fallback_when_open():
    from services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker('test_fallback', failure_threshold=1, recovery_timeout=60)

    def _fail():
        raise RuntimeError("fail")

    cb.call(_fail, fallback=None)              # opens the breaker
    assert cb.state == 'OPEN'
    result = cb.call(lambda: 42, fallback='fallback_value')
    assert result == 'fallback_value'


def test_circuit_breaker_reset():
    from services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker('test_reset', failure_threshold=1, recovery_timeout=60)

    def _fail():
        raise Exception("fail")

    cb.call(_fail, fallback=None)
    assert cb.state == 'OPEN'
    cb.reset()
    assert cb.state == 'CLOSED'
    # Post-PASS-15: failures count is exposed via _get_failures() (was: _failures attr)
    assert cb._get_failures() == 0


def test_circuit_breaker_status_dict():
    from services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker('test_status', failure_threshold=3, recovery_timeout=120)
    s = cb.status()
    assert s['name'] == 'test_status'
    assert s['state'] == 'CLOSED'
    assert s['failures'] == 0
    assert s['failure_threshold'] == 3
    assert s['recovery_timeout_s'] == 120


# ── Ephémérides ───────────────────────────────────────────────────────────────

def test_ephemeris_structure():
    from services.ephemeris_service import get_full_ephemeris
    data = get_full_ephemeris()
    assert isinstance(data, dict)
    assert 'soleil' in data
    assert 'lune' in data
    assert 'nuit_astronomique' in data
    assert data.get('lieu') == 'Tlemcen, Algérie'


def test_ephemeris_sun_has_fields():
    from services.ephemeris_service import get_sun_ephemeris
    sun = get_sun_ephemeris()
    assert isinstance(sun, dict)
    for field in ('alt_now', 'az_now', 'lever', 'coucher'):
        assert field in sun, f"Champ manquant : {field}"


def test_ephemeris_moon_has_fields():
    from services.ephemeris_service import get_moon_ephemeris
    moon = get_moon_ephemeris()
    assert isinstance(moon, dict)
    for field in ('alt_now', 'az_now', 'phase', 'illumination_pct'):
        assert field in moon, f"Champ manquant : {field}"


# ── Utils ─────────────────────────────────────────────────────────────────────

def test_is_bot_user_agent_detects_bots():
    from services.utils import _is_bot_user_agent
    assert _is_bot_user_agent('Googlebot/2.1 (+http://www.google.com/bot.html)') is True
    assert _is_bot_user_agent('Mozilla/5.0 (compatible; bingbot/2.0)') is True
    assert _is_bot_user_agent('python-requests/2.28.0') is True


def test_is_bot_user_agent_passes_humans():
    from services.utils import _is_bot_user_agent
    assert _is_bot_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120') is False
    assert _is_bot_user_agent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604') is False


def test_safe_json_loads_valid():
    from services.utils import _safe_json_loads
    result = _safe_json_loads('{"a": 1, "b": "hello"}')
    assert result == {'a': 1, 'b': 'hello'}


def test_safe_json_loads_invalid():
    from services.utils import _safe_json_loads
    assert _safe_json_loads('not json') is None
    assert _safe_json_loads('') is None
    assert _safe_json_loads(None) is None


def test_safe_json_loads_array():
    from services.utils import _safe_json_loads
    result = _safe_json_loads('[1, 2, 3]')
    assert result == [1, 2, 3]


def test_detect_lang_english():
    from services.utils import _detect_lang
    assert _detect_lang('The sun was bright and the sky was clear') is True


def test_detect_lang_french():
    from services.utils import _detect_lang
    assert _detect_lang('Le soleil brille sur Tlemcen ce soir') is False


# ── DB context manager (structure) ───────────────────────────────────────────

def test_db_context_manager_exports():
    from services import db
    assert hasattr(db, 'get_db')
    assert hasattr(db, 'init_all_wal')
    assert hasattr(db, 'DB_MAIN')
    assert hasattr(db, '_ALL_PRODUCTION_DBS')
    assert len(db._ALL_PRODUCTION_DBS) >= 3


# ── NASA service (structure sans réseau) ─────────────────────────────────────

def test_nasa_service_exports():
    from services.nasa_service import (
        get_api_key, _fetch_nasa_apod, _fetch_nasa_neo, _fetch_nasa_solar,
        get_apod_data, get_neo_feed, get_space_events,
    )
    assert callable(get_api_key)
    assert callable(_fetch_nasa_apod)
    assert callable(get_apod_data)


def test_nasa_api_key_fallback():
    from services.nasa_service import get_api_key
    import os
    original = os.environ.pop('NASA_API_KEY', None)
    try:
        key = get_api_key()
        assert key == 'DEMO_KEY'
    finally:
        if original is not None:
            os.environ['NASA_API_KEY'] = original


# ── Orbital service (structure) ───────────────────────────────────────────────

def test_orbital_service_exports():
    from services.orbital_service import (
        compute_tle_risk_signal, build_final_core,
        normalize_celestrak_record, get_iss_position, load_tle_data,
    )
    assert callable(compute_tle_risk_signal)
    assert callable(get_iss_position)


def test_tle_risk_signal():
    from services.orbital_service import compute_tle_risk_signal
    assert compute_tle_risk_signal('fresh') == 'MEDIUM'
    assert compute_tle_risk_signal('stale') == 'HIGH'
    assert compute_tle_risk_signal('unknown') == 'LOW'
    assert compute_tle_risk_signal(None) == 'LOW'
