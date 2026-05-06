"""Layer 1 — OpenSky filed flight plan.

Calls /api/flights/aircraft (requires OAuth2 token, available since 2024).
The endpoint returns recent flight legs for an icao24 within a time window;
we pick the most recent leg ending in the future or still in progress.

Cache: as:fr:flightplan:<icao24> TTL 1h.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from app.blueprints.flight_radar.services.opensky_client import (
    USER_AGENT,
    get_client,
)

log = logging.getLogger(__name__)

FLIGHTS_URL = "https://opensky-network.org/api/flights/aircraft"
CACHE_TTL = 3600  # 1 hour


def fetch_flight_plan(
    icao24: str,
    redis_client: Any | None = None,
    hours_back: int = 12,
) -> dict[str, Any] | None:
    """Return {departure_icao, arrival_icao, callsign, first_seen_ts, last_seen_ts}
    or None if not available.
    """
    icao24 = (icao24 or "").lower().strip()
    if not icao24:
        return None
    cache_key = f"as:fr:flightplan:{icao24}"

    # Cached value (None or dict serialized)
    if redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
            if cached is not None:
                return json.loads(cached) if cached != "null" else None
        except Exception:
            pass

    cli = get_client()
    token = cli.get_token()
    if not token:
        # No token = can't call /flights/aircraft (it requires auth).
        return None

    end_ts = int(time.time())
    begin_ts = end_ts - hours_back * 3600

    try:
        r = requests.get(
            FLIGHTS_URL,
            params={"icao24": icao24, "begin": begin_ts, "end": end_ts},
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
            },
            timeout=10,
        )
        if r.status_code != 200:
            log.debug("[algo7.layer1] %s for %s", r.status_code, icao24)
            if redis_client is not None:
                try:
                    redis_client.setex(cache_key, 600, "null")
                except Exception:
                    pass
            return None
        flights = r.json()
        if not isinstance(flights, list) or not flights:
            if redis_client is not None:
                try:
                    redis_client.setex(cache_key, 600, "null")
                except Exception:
                    pass
            return None
        # Pick the most recent leg with a destination known.
        flights.sort(key=lambda f: f.get("lastSeen") or 0, reverse=True)
        for fl in flights:
            dep = fl.get("estDepartureAirport")
            arr = fl.get("estArrivalAirport")
            if not (dep or arr):
                continue
            result = {
                "departure_icao": dep,
                "arrival_icao": arr,
                "callsign": (fl.get("callsign") or "").strip(),
                "first_seen_ts": fl.get("firstSeen"),
                "last_seen_ts": fl.get("lastSeen"),
            }
            if redis_client is not None:
                try:
                    redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))
                except Exception:
                    pass
            return result
        # No usable leg
        if redis_client is not None:
            try:
                redis_client.setex(cache_key, 600, "null")
            except Exception:
                pass
        return None
    except Exception as exc:
        log.debug("[algo7.layer1] request failed: %s", exc)
        return None
