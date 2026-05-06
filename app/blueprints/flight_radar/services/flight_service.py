"""FlightService — background poll loop + Redis cache.

Layout in Redis:
  as:fr:aircraft               hash  {icao24 -> JSON state}
  as:fr:aircraft_history:<id>  list  LPUSH max 30 (last positions)
  as:fr:aircraft_first_seen    hash  {icao24 -> first_seen_ts}, TTL 24h
  as:fr:fetch_meta             hash  {ts, count, source}

Multi-worker safety (Gunicorn 4-worker setup):
  Only ONE worker may poll OpenSky at a time — OpenSky rate-limits a
  single OAuth2 client with 429s when 4 workers poll in parallel using
  the same key. Election is done via a Redis distributed lock
  (SET NX EX, refreshed by a heartbeat thread). Other workers stay in
  standby and only read from the cache populated by the elected worker.

  - LOCK_KEY    : astroscan:lock:opensky_poller
  - LOCK_TTL    : 90 s (heartbeat refresh every 30 s)
  - On lock loss the elected worker stops polling and re-enters the
    standby loop. A dead worker stops refreshing → another worker
    elects itself within ~LOCK_TTL.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import uuid
from functools import lru_cache
from typing import Any

from app.blueprints.flight_radar.services.aircraft_enrichment import (
    format_callsign,
    icao24_to_country,
    is_invalid_aircraft_value,
)
from app.blueprints.flight_radar.services.opensky_client import OpenSkyClient

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 30
HISTORY_MAX = 30
FIRST_SEEN_TTL = 24 * 3600

EARTH_R_KM = 6371.0
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AIRPORTS_PATH = os.path.join(_BASE_DIR, "data", "airports_geo.json")

# ──────────────────────────────────────────────────────────────────────
# Distributed lock (Redis SET NX EX) — same pattern as AISStream
# ──────────────────────────────────────────────────────────────────────

WORKER_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

LOCK_KEY = "astroscan:lock:opensky_poller"
LOCK_TTL = 90              # seconds — survives a Gunicorn graceful timeout
HEARTBEAT_INTERVAL = 30    # refresh cadence (LOCK_TTL / 3 — comfortable margin)
STANDBY_RETRY_INTERVAL = 60  # how long a non-elected worker sleeps between probes

# Backoff escalation when receiving consecutive 429s while holding the lock.
RATE_LIMIT_BACKOFF_THRESHOLD = 3   # after N consecutive 429s, slow down
RATE_LIMIT_EXTRA_WAIT = 60         # extra seconds between polls when throttled

# Atomic refresh: only refresh if we still own the key.
_LUA_REFRESH = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
"""

# Atomic release: only DEL if we own the key.
_LUA_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def try_acquire_lock(redis_client) -> bool:
    """Attempt to become the OpenSky poller. True if elected."""
    if redis_client is None:
        return False
    try:
        return bool(redis_client.set(LOCK_KEY, WORKER_ID, nx=True, ex=LOCK_TTL))
    except Exception as exc:
        log.warning("[flight_radar] OpenSky lock acquire failed: %s", exc)
        return False


def refresh_lock(redis_client) -> bool:
    """Refresh the lock TTL if we still own it. Atomic via Lua."""
    if redis_client is None:
        return False
    try:
        return redis_client.eval(_LUA_REFRESH, 1, LOCK_KEY, WORKER_ID, LOCK_TTL) == 1
    except Exception as exc:
        log.warning("[flight_radar] OpenSky lock refresh failed: %s", exc)
        return False


def release_lock(redis_client) -> None:
    """Release the lock if we own it. No-op otherwise (atomic via Lua)."""
    if redis_client is None:
        return
    try:
        redis_client.eval(_LUA_RELEASE, 1, LOCK_KEY, WORKER_ID)
    except Exception:
        pass


def _read_lock_holder(redis_client) -> str | None:
    if redis_client is None:
        return None
    try:
        v = redis_client.get(LOCK_KEY)
        if v is None:
            return None
        return v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _airports_index() -> dict[str, dict[str, Any]]:
    try:
        with open(_AIRPORTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for ap in data:
        # IATA is the primary key (3-letter), ICAO secondary (4-letter).
        if ap.get("iata"):
            out[ap["iata"].upper()] = ap
        if ap.get("icao"):
            out[ap["icao"].upper()] = ap
    return out


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def _safe_state(s: list[Any]) -> dict[str, Any] | None:
    """Map an OpenSky state-vector array into a normalized dict.

    Index reference (https://openskynetwork.github.io/opensky-api/rest.html):
      0 icao24, 1 callsign, 2 origin_country, 3 time_position,
      4 last_contact, 5 longitude, 6 latitude, 7 baro_altitude,
      8 on_ground, 9 velocity, 10 true_track, 11 vertical_rate,
      12 sensors, 13 geo_altitude, 14 squawk, 15 spi, 16 position_source.
    """
    if not isinstance(s, list) or len(s) < 11:
        return None
    icao24 = (s[0] or "").lower().strip()
    if not icao24:
        return None
    lon = s[5]
    lat = s[6]
    if is_invalid_aircraft_value(lat) or is_invalid_aircraft_value(lon):
        return None
    return {
        "icao24": icao24,
        "callsign": format_callsign(s[1]),
        "origin_country": s[2] or "",
        "time_position": s[3],
        "last_contact": s[4],
        "lon": float(lon),
        "lat": float(lat),
        "baro_altitude": s[7],
        "on_ground": bool(s[8]) if s[8] is not None else False,
        "velocity": s[9],
        "true_track": s[10],
        "vertical_rate": s[11],
        "geo_altitude": s[13] if len(s) > 13 else None,
        "squawk": (s[14] or "").strip() if len(s) > 14 and s[14] else None,
        "spi": bool(s[15]) if len(s) > 15 and s[15] is not None else False,
    }


class FlightService:
    def __init__(self, redis_client: Any, opensky: OpenSkyClient) -> None:
        self.redis = redis_client
        self.opensky = opensky
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_payload: dict[str, Any] = {
            "ts": 0,
            "count": 0,
            "source": "init",
        }
        # In-memory mirror of the cache (used when Redis is down).
        self._mem_cache: dict[str, dict[str, Any]] = {}
        self._mem_history: dict[str, list[dict[str, float]]] = {}
        self._first_seen: dict[str, int] = {}

        # Multi-worker lock state
        self.is_elected: bool = False
        self._lock_lost_event: threading.Event = threading.Event()
        self._heartbeat_stop: threading.Event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        # Counter for consecutive 429s to back off when throttled
        self._consecutive_429: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._poll_loop,
                name="flight-radar-poll",
                daemon=True,
            )
            self._thread.start()
            log.info(
                "[flight_radar] poll loop started (every %ds, worker_id=%s)",
                POLL_INTERVAL_S, WORKER_ID,
            )

    def stop(self) -> None:
        self._stop.set()
        self._heartbeat_stop.set()
        if self.is_elected:
            release_lock(self.redis)
            self.is_elected = False

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Election-aware poll loop.

        Phase 1 — election: try to acquire the Redis lock. If another
        worker holds it, sleep STANDBY_RETRY_INTERVAL and retry. We never
        give up: if the elected worker dies, its lock TTL expires and we
        take over.

        Phase 2 — polling: holding the lock, start the heartbeat thread
        and run the 30 s OpenSky poll. On lock loss we abandon polling
        and go back to phase 1.
        """
        last_standby_log = 0.0
        while not self._stop.is_set():
            # ---------- Phase 1: election ----------
            if not try_acquire_lock(self.redis):
                holder = _read_lock_holder(self.redis)
                now_ts = time.time()
                if now_ts - last_standby_log > 300:
                    log.info(
                        "[flight_radar] OpenSky poll lock held by worker %s, "
                        "standby (worker_id=%s)",
                        holder or "?", WORKER_ID,
                    )
                    last_standby_log = now_ts
                self._stop.wait(STANDBY_RETRY_INTERVAL)
                continue

            # We won the election.
            self.is_elected = True
            self._lock_lost_event.clear()
            self._heartbeat_stop.clear()
            self._consecutive_429 = 0
            log.info(
                "[flight_radar] OpenSky poll lock acquired by worker %s",
                WORKER_ID,
            )

            # Start heartbeat (refresh lock every HEARTBEAT_INTERVAL s).
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                name="flight-radar-heartbeat",
                daemon=True,
            )
            self._heartbeat_thread.start()

            # ---------- Phase 2: poll while elected ----------
            try:
                while not self._stop.is_set() and not self._lock_lost_event.is_set():
                    rate_limited_before = int(
                        self.opensky.metrics.get("rate_limited") or 0
                    )
                    try:
                        self._fetch_once()
                    except Exception as exc:  # pragma: no cover
                        log.exception("[flight_radar] poll loop error: %s", exc)

                    rate_limited_after = int(
                        self.opensky.metrics.get("rate_limited") or 0
                    )
                    if rate_limited_after > rate_limited_before:
                        self._consecutive_429 += 1
                    else:
                        self._consecutive_429 = 0

                    wait = POLL_INTERVAL_S
                    if self._consecutive_429 >= RATE_LIMIT_BACKOFF_THRESHOLD:
                        wait = POLL_INTERVAL_S + RATE_LIMIT_EXTRA_WAIT
                        log.warning(
                            "[flight_radar] %d consecutive 429s — extending "
                            "poll interval to %ds (worker %s)",
                            self._consecutive_429, wait, WORKER_ID,
                        )
                    self._stop.wait(wait)

                if self._lock_lost_event.is_set() and not self._stop.is_set():
                    log.warning(
                        "[flight_radar] OpenSky poll lock lost — "
                        "worker %s returns to standby", WORKER_ID,
                    )
            finally:
                # Tear down heartbeat regardless of outcome.
                self._heartbeat_stop.set()
                if self._heartbeat_thread is not None:
                    try:
                        self._heartbeat_thread.join(timeout=2)
                    except Exception:
                        pass
                    self._heartbeat_thread = None
                self.is_elected = False

        # On shutdown: best-effort lock release so a sibling worker can
        # take over without waiting for TTL expiry.
        release_lock(self.redis)

    def _heartbeat_loop(self) -> None:
        """Refresh the Redis lock periodically.

        If a refresh fails (TTL expired, lock taken by another worker, or
        Redis blip), we set _lock_lost_event so the poll loop exits.
        """
        while not self._heartbeat_stop.is_set() and not self._stop.is_set():
            if not refresh_lock(self.redis):
                log.warning(
                    "[flight_radar] OpenSky lock refresh failed — "
                    "yielding (worker %s)", WORKER_ID,
                )
                self._lock_lost_event.set()
                return
            self._heartbeat_stop.wait(HEARTBEAT_INTERVAL)

    def _fetch_once(self) -> None:
        payload = self.opensky.fetch_states()
        if not payload or not isinstance(payload, dict):
            return
        states = payload.get("states") or []
        ts_now = int(time.time())
        snapshot: dict[str, dict[str, Any]] = {}
        for s in states:
            mapped = _safe_state(s)
            if not mapped:
                continue
            mapped["ts"] = ts_now
            snapshot[mapped["icao24"]] = mapped

        # Persist
        if self.redis is not None:
            try:
                pipe = self.redis.pipeline()
                pipe.delete("as:fr:aircraft")
                if snapshot:
                    pipe.hset(
                        "as:fr:aircraft",
                        mapping={k: json.dumps(v) for k, v in snapshot.items()},
                    )
                pipe.expire("as:fr:aircraft", 120)
                pipe.hset(
                    "as:fr:fetch_meta",
                    mapping={
                        "ts": ts_now,
                        "count": len(snapshot),
                        "source": "opensky",
                    },
                )
                pipe.expire("as:fr:fetch_meta", 300)
                pipe.execute()
                # History — push recent point per aircraft.
                hist_pipe = self.redis.pipeline()
                for icao24, st in snapshot.items():
                    point = {
                        "lat": st["lat"],
                        "lon": st["lon"],
                        "alt": st.get("baro_altitude") or st.get("geo_altitude"),
                        "ts": ts_now,
                    }
                    key = f"as:fr:aircraft_history:{icao24}"
                    hist_pipe.lpush(key, json.dumps(point))
                    hist_pipe.ltrim(key, 0, HISTORY_MAX - 1)
                    hist_pipe.expire(key, 1800)
                    # First-seen tracking
                    hist_pipe.hsetnx("as:fr:aircraft_first_seen", icao24, ts_now)
                hist_pipe.expire("as:fr:aircraft_first_seen", FIRST_SEEN_TTL)
                hist_pipe.execute()
            except Exception as exc:
                log.warning("[flight_radar] redis write failed: %s", exc)
                self._update_mem_cache(snapshot, ts_now)
        else:
            self._update_mem_cache(snapshot, ts_now)

        self._last_payload = {
            "ts": ts_now,
            "count": len(snapshot),
            "source": "opensky",
        }
        log.info(
            "[flight_radar] fetched %d aircraft (auth=%s)",
            len(snapshot),
            self.opensky.metrics.get("auth_mode"),
        )

    def _update_mem_cache(self, snapshot: dict[str, dict[str, Any]], ts_now: int) -> None:
        self._mem_cache = snapshot
        for icao24, st in snapshot.items():
            point = {
                "lat": st["lat"],
                "lon": st["lon"],
                "alt": st.get("baro_altitude") or st.get("geo_altitude"),
                "ts": ts_now,
            }
            hist = self._mem_history.setdefault(icao24, [])
            hist.insert(0, point)
            del hist[HISTORY_MAX:]
            self._first_seen.setdefault(icao24, ts_now)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_aircraft_list(
        self,
        country_iso: str | None = None,
        on_ground: str | None = None,
        alt_min: float | None = None,
        alt_max: float | None = None,
        limit: int = 800,
    ) -> dict[str, Any]:
        snap = self._read_snapshot()
        items: list[dict[str, Any]] = []
        for st in snap.values():
            if on_ground == "fly" and st.get("on_ground"):
                continue
            if on_ground == "gnd" and not st.get("on_ground"):
                continue
            alt = st.get("baro_altitude") or st.get("geo_altitude") or 0
            if alt_min is not None and (alt or 0) < alt_min:
                continue
            if alt_max is not None and (alt or 0) > alt_max:
                continue
            if country_iso:
                country = icao24_to_country(st.get("icao24"))
                if not country or country.get("iso") != country_iso.upper():
                    continue
            items.append(st)
        # Cap rendering — if Redis returned >limit, keep the most recent.
        items.sort(key=lambda x: x.get("last_contact") or 0, reverse=True)
        meta = self._read_meta()
        return {
            "aircraft": items[:limit],
            "total": len(snap),
            "rendered": min(len(items), limit),
            "ts": meta.get("ts", self._last_payload.get("ts")),
            "source": meta.get("source", "opensky"),
        }

    def get_aircraft_state(self, icao24: str) -> dict[str, Any] | None:
        icao24 = (icao24 or "").lower().strip()
        if not icao24:
            return None
        snap = self._read_snapshot()
        st = snap.get(icao24)
        if not st:
            return None
        st = dict(st)
        st["country"] = icao24_to_country(icao24)
        st["track"] = self.get_track(icao24)
        st["first_seen"] = self._read_first_seen(icao24)
        return st

    def get_airport_details(self, iata_or_icao: str) -> dict[str, Any] | None:
        """Live airport HUD data: identification + position + traffic within 100 km."""
        key = (iata_or_icao or "").upper().strip()
        if not key:
            return None
        ap = _airports_index().get(key)
        if not ap:
            return None

        snap = self._read_snapshot()
        approaching: list[dict[str, Any]] = []
        departing: list[dict[str, Any]] = []
        on_ground: list[dict[str, Any]] = []
        transit: list[dict[str, Any]] = []

        for icao24, st in snap.items():
            try:
                lat = float(st.get("lat"))
                lon = float(st.get("lon"))
            except (TypeError, ValueError):
                continue
            d = _haversine_km(lat, lon, float(ap["lat"]), float(ap["lon"]))
            if d > 100:
                continue

            alt = st.get("baro_altitude") or st.get("geo_altitude") or 0
            try:
                alt = float(alt)
            except (TypeError, ValueError):
                alt = 0.0
            vario_ms = st.get("vertical_rate") or 0
            try:
                vario_ms = float(vario_ms)
            except (TypeError, ValueError):
                vario_ms = 0.0
            vario_fpm = vario_ms * 196.85
            speed_ms = st.get("velocity") or 0
            try:
                speed_ms = float(speed_ms)
            except (TypeError, ValueError):
                speed_ms = 0.0

            entry = {
                "callsign": st.get("callsign") or icao24.upper(),
                "icao24": icao24,
                "distance_km": round(d, 1),
                "alt_m": int(alt) if alt else 0,
                "vario_fpm": int(vario_fpm),
                "speed_kmh": int(speed_ms * 3.6),
                "true_track": st.get("true_track"),
                "lat": st.get("lat"),
                "lon": st.get("lon"),
            }

            if alt < 100 or speed_ms < 20 or st.get("on_ground"):
                on_ground.append(entry)
            elif vario_fpm < -300 and alt < 5000 and d < 50:
                approaching.append(entry)
            elif vario_fpm > 500 and alt < 5000 and d < 30:
                departing.append(entry)
            else:
                transit.append(entry)

        # Sort each list by distance (or vario for departures).
        approaching.sort(key=lambda e: e["distance_km"])
        departing.sort(key=lambda e: e["distance_km"])
        on_ground.sort(key=lambda e: e["distance_km"])
        transit.sort(key=lambda e: e["distance_km"])

        total = len(approaching) + len(departing) + len(on_ground) + len(transit)

        return {
            "airport": {
                "iata": ap.get("iata"),
                "icao": ap.get("icao"),
                "name_fr": ap.get("name_fr"),
                "name_en": ap.get("name_en"),
                "city": ap.get("city"),
                "country_iso": ap.get("country_iso"),
                "lat": ap.get("lat"),
                "lon": ap.get("lon"),
                "altitude_m": ap.get("altitude_m"),
                "timezone": ap.get("timezone"),
            },
            "live_traffic": {
                "aircraft_within_100km": total,
                "approaching": approaching[:20],
                "departing": departing[:20],
                "on_ground": on_ground[:20],
                "transit": transit[:30],
            },
            "stats_summary": {
                "approaching_count": len(approaching),
                "departing_count": len(departing),
                "on_ground_count": len(on_ground),
                "transit_count": len(transit),
                "total_within_100km": total,
            },
        }

    def get_track(self, icao24: str, limit: int = 30) -> list[dict[str, float]]:
        icao24 = (icao24 or "").lower().strip()
        if not icao24:
            return []
        if self.redis is not None:
            try:
                raw = self.redis.lrange(
                    f"as:fr:aircraft_history:{icao24}", 0, limit - 1
                )
                return [json.loads(x) for x in raw if x]
            except Exception as exc:
                log.warning("[flight_radar] track read failed: %s", exc)
        return list(self._mem_history.get(icao24, []))[:limit]

    # ------------------------------------------------------------------
    # Internal reads
    # ------------------------------------------------------------------

    def _read_snapshot(self) -> dict[str, dict[str, Any]]:
        if self.redis is not None:
            try:
                raw = self.redis.hgetall("as:fr:aircraft") or {}
                return {k: json.loads(v) for k, v in raw.items() if v}
            except Exception as exc:
                log.warning("[flight_radar] snapshot read failed: %s", exc)
        return dict(self._mem_cache)

    def _read_meta(self) -> dict[str, Any]:
        if self.redis is not None:
            try:
                raw = self.redis.hgetall("as:fr:fetch_meta") or {}
                if raw:
                    return {
                        "ts": int(raw.get("ts") or 0),
                        "count": int(raw.get("count") or 0),
                        "source": raw.get("source") or "",
                    }
            except Exception:
                pass
        return dict(self._last_payload)

    def _read_first_seen(self, icao24: str) -> int | None:
        if self.redis is not None:
            try:
                v = self.redis.hget("as:fr:aircraft_first_seen", icao24)
                return int(v) if v else None
            except Exception:
                pass
        return self._first_seen.get(icao24)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        meta = self._read_meta()
        snap = self._read_snapshot()
        return {
            "ok": True,
            "auth_mode": self.opensky.metrics.get("auth_mode"),
            "token_expires_in": self.opensky.metrics.get("token_expires_in"),
            "calls": self.opensky.metrics.get("calls"),
            "errors": self.opensky.metrics.get("errors"),
            "rate_limited": self.opensky.metrics.get("rate_limited"),
            "last_success_ts": self.opensky.metrics.get("last_success_ts"),
            "last_error": self.opensky.metrics.get("last_error"),
            "cache_size": len(snap),
            "fetch_meta": meta,
            "redis": self.redis is not None,
            # Multi-worker lock state
            "worker_id": WORKER_ID,
            "is_elected": self.is_elected,
            "lock_holder": _read_lock_holder(self.redis),
            "lock_key": LOCK_KEY,
            "lock_ttl": LOCK_TTL,
            "consecutive_429": self._consecutive_429,
            "scrapingbee_used": self.opensky.metrics.get("scrapingbee_used"),
            "scrapingbee_calls": self.opensky.metrics.get("scrapingbee_calls"),
            "scrapingbee_errors": self.opensky.metrics.get("scrapingbee_errors"),
            "adsblol_used": self.opensky.metrics.get("adsblol_used"),
            "adsblol_calls": self.opensky.metrics.get("adsblol_calls"),
            "adsblol_errors": self.opensky.metrics.get("adsblol_errors"),
            "current_source": self.opensky.metrics.get("current_source"),
        }
