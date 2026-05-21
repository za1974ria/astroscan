"""Régression — Constantes observatoire Tlemcen.

Bug historique : longitude écrite +1.32°E (Tiaret, ~300 km est) au lieu de
-1.3167°W (Tlemcen). Ces tests verrouillent la valeur correcte.
"""

from __future__ import annotations

import math

import pytest

from app.constants import observatory as obs

pytestmark = pytest.mark.unit


def test_observer_lat_is_correct_tlemcen():
    assert obs.OBSERVER_LAT == pytest.approx(34.8753, abs=1e-4)


def test_observer_lon_is_negative_west_of_greenwich():
    assert obs.OBSERVER_LON < 0, "Tlemcen is WEST of Greenwich — longitude must be negative"
    assert obs.OBSERVER_LON == pytest.approx(-1.3167, abs=1e-4)


def test_observer_lon_never_positive_eastern_tiaret_bug():
    assert obs.OBSERVER_LON != pytest.approx(1.32, abs=0.05), (
        "Historical bug: +1.32 places station at Tiaret, ~300km east of Tlemcen"
    )


def test_observer_alt_in_realistic_range():
    assert 750 <= obs.OBSERVER_ALT_M <= 900


def test_observer_city_and_country():
    assert "Tlemcen" in obs.OBSERVER_CITY
    assert obs.OBSERVER_COUNTRY == "DZ"


def test_observer_timezone_north_africa():
    assert obs.OBSERVER_TIMEZONE == "Africa/Algiers"


def test_legacy_aliases_match():
    assert obs.TLEMCEN_LAT == obs.OBSERVER_LAT
    assert obs.TLEMCEN_LON == obs.OBSERVER_LON
    assert obs.TLEMCEN_ALT == obs.OBSERVER_ALT_M


def test_observer_dict_consistency():
    assert obs.OBSERVER_DICT["city"] == obs.OBSERVER_CITY
    assert obs.OBSERVER_DICT["country"] == obs.OBSERVER_COUNTRY
    assert obs.OBSERVER_DICT.get("lat", obs.OBSERVER_LAT) == obs.OBSERVER_LAT
    assert obs.OBSERVER_DICT.get("lon", obs.OBSERVER_LON) == obs.OBSERVER_LON


def test_distance_to_tiaret_proves_lon_west():
    """Sanity check: |Tlemcen → Tiaret| ≈ 300 km (great-circle).
    If lon were +1.32 by mistake, we'd be sitting on Tiaret."""
    tiaret_lat, tiaret_lon = 35.3711, 1.3162
    R = 6371.0
    phi1, phi2 = math.radians(obs.OBSERVER_LAT), math.radians(tiaret_lat)
    dphi = math.radians(tiaret_lat - obs.OBSERVER_LAT)
    dlam = math.radians(tiaret_lon - obs.OBSERVER_LON)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    d_km = 2 * R * math.asin(math.sqrt(a))
    assert 200 < d_km < 400, f"Tlemcen→Tiaret distance should be ~300km, got {d_km:.0f}km"
