"""SCAN A SIGNAL — satellite tracking service.

Reads the existing astroscan TLE catalogue (data/tle/active.tle, ~9000 lines,
~1000+ live satellites). Uses Skyfield's SGP4 propagator to compute live
position/velocity/orbital state, ground tracks, next passes over Tlemcen,
and per-antenna reception (RSSI, elevation) using the
12 ASTRO-SCAN observatories defined in ground_assets/observatories.json.

Single instance — TLE parsed once at construction, refreshed on demand.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from skyfield.api import EarthSatellite, load, wgs84

from app.blueprints.scan_signal.services.radio_propagation import (
    haversine_km,
    rssi_estimate_dbm,
    satellite_elevation_deg,
    slant_range_km,
)

log = logging.getLogger(__name__)

# Candidate TLE locations — tried in order, first non-empty wins.
_TLE_PATHS = (
    "/root/astro_scan/data/tle/active.tle",
    "/root/astro_scan/data/tle/active.txt",
    "/root/astro_scan/data/tle/celestrak.txt",
)

_OBS_PATH = "/root/astro_scan/app/blueprints/ground_assets/observatories.json"
_POPULAR_PATH = "/root/astro_scan/app/blueprints/scan_signal/data/popular_satellites.json"

# Drop TLEs whose epoch is older than this many days. SGP4 propagation
# beyond ~2 weeks compounds error; 30 d is a conservative cutoff that
# also excludes pre-launch/synthetic placeholder TLEs (epoch in 1970s).
_TLE_FRESH_THRESHOLD_DAYS = 30.0

# Owner observatory — used for "next pass" computations.
_TLEMCEN_LAT = 34.87
_TLEMCEN_LON = -1.32
_TLEMCEN_ELEV_M = 800.0

# Antenna reception cap — top-N strongest antennas returned per satellite.
_ANTENNA_TOP_N = 5
_ANTENNA_MIN_ELEV = 0.0  # only above horizon
_ANTENNA_DEFAULT_FREQ_MHZ = 437.5
# Effective Isotropic Radiated Power (dBm) — represents the satellite's
# transmitter plus antenna gains plus ground-station antenna gain. 50 dBm
# (~100W EIRP) is in the realistic range for amateur/CubeSat downlinks
# received by a yagi/dish + LNA at the ground station.
_ANTENNA_DEFAULT_TX_DBM = 50.0


class SatelliteService:
    """SGP4 satellite tracking, mission-control grade."""

    def __init__(self) -> None:
        self.ts = load.timescale()
        self._satellites: list[EarthSatellite] = []
        self._index: dict[int, EarthSatellite] = {}
        self._tle_path: str | None = None
        self._tle_loaded_at: datetime | None = None
        # TLE freshness counters
        self._raw_count: int = 0
        self._fresh_count: int = 0
        self._obsolete_count: int = 0
        self._tle_age_avg_days: float = 0.0
        self._tle_oldest_fresh_days: float = 0.0
        self._lock = threading.Lock()
        self._observatories: list[dict] = []
        # Curated popular catalogue + alias map
        self._popular: list[dict] = []
        self._popular_aliases: dict[str, int] = {}
        self._load_observatories()
        self._load_popular()
        self._load_tle()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _load_observatories(self) -> None:
        try:
            with open(_OBS_PATH, "r", encoding="utf-8") as f:
                self._observatories = json.load(f)
            log.info("[scan_signal] loaded %d observatories", len(self._observatories))
        except Exception as exc:
            log.warning("[scan_signal] failed to load observatories: %s", exc)
            self._observatories = []

    def _load_popular(self) -> None:
        try:
            with open(_POPULAR_PATH, "r", encoding="utf-8") as f:
                self._popular = json.load(f)
        except Exception as exc:
            log.warning("[scan_signal] failed to load popular catalogue: %s", exc)
            self._popular = []
        # Build alias map: name + alias (lowercased) -> norad
        for p in self._popular:
            try:
                norad = int(p.get("norad"))
            except (TypeError, ValueError):
                continue
            name = (p.get("name") or "").strip().lower()
            alias = (p.get("alias") or "").strip().lower()
            if name:
                self._popular_aliases[name] = norad
            if alias:
                self._popular_aliases[alias] = norad
        log.info("[scan_signal] popular aliases registered: %d", len(self._popular_aliases))

    def _load_tle(self) -> None:
        path = next((p for p in _TLE_PATHS if os.path.isfile(p) and os.path.getsize(p) > 0), None)
        if not path:
            log.error("[scan_signal] no TLE file found in %s", _TLE_PATHS)
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = [ln.rstrip("\r\n") for ln in f.readlines()]
        except Exception as exc:
            log.error("[scan_signal] failed to read TLE %s: %s", path, exc)
            return

        sats: list[EarthSatellite] = []
        index: dict[int, EarthSatellite] = {}
        ages_days: list[float] = []
        raw_count = 0
        fresh_count = 0
        obsolete_count = 0
        now = datetime.now(timezone.utc)

        # Standard 3-line TLE format: NAME / line1 / line2
        i = 0
        n = len(lines)
        while i < n - 2:
            name = lines[i].strip()
            l1 = lines[i + 1].strip()
            l2 = lines[i + 2].strip()
            if not (l1.startswith("1 ") and l2.startswith("2 ")):
                i += 1
                continue
            i += 3
            raw_count += 1
            try:
                sat = EarthSatellite(l1, l2, name, self.ts)
            except Exception:
                obsolete_count += 1
                continue
            try:
                age_days = (now - sat.epoch.utc_datetime()).total_seconds() / 86400.0
            except Exception:
                obsolete_count += 1
                continue
            if age_days < 0 or age_days > _TLE_FRESH_THRESHOLD_DAYS:
                obsolete_count += 1
                continue
            try:
                norad = int(sat.model.satnum)
            except Exception:
                obsolete_count += 1
                continue
            sats.append(sat)
            index[norad] = sat
            ages_days.append(age_days)
            fresh_count += 1

        avg = (sum(ages_days) / len(ages_days)) if ages_days else 0.0
        oldest_fresh = max(ages_days) if ages_days else 0.0

        with self._lock:
            self._satellites = sats
            self._index = index
            self._tle_path = path
            self._tle_loaded_at = now
            self._raw_count = raw_count
            self._fresh_count = fresh_count
            self._obsolete_count = obsolete_count
            self._tle_age_avg_days = avg
            self._tle_oldest_fresh_days = oldest_fresh

        log.info(
            "[scan_signal] TLE loaded: %d fresh / %d obsolete skipped "
            "(raw=%d, avg_age=%.1fd, oldest_fresh=%.1fd) from %s",
            fresh_count, obsolete_count, raw_count, avg, oldest_fresh, path,
        )

    # ------------------------------------------------------------------
    # Public API — search
    # ------------------------------------------------------------------

    def search(self, query: str) -> dict[str, Any]:
        """Search by NORAD ID, popular alias, then substring on TLE name.

        Hierarchy:
          1. exact NORAD ID
          2. exact / substring match against curated popular aliases
             (e.g. "TIANGONG" -> 48274 -> "CSS (TIANHE-1)" in the TLE catalogue)
          3. substring match against the live TLE names
        """
        q = (query or "").strip()
        if not q:
            return {"query": q, "matches": [], "total_found": 0, "showing": 0}

        q_lower = q.lower()
        matches: list[dict] = []
        seen: set[int] = set()
        total = 0

        def _push(norad: int) -> None:
            sat = self._index.get(norad)
            if sat is None or norad in seen:
                return
            matches.append({
                "norad": norad,
                "name": sat.name,
                "type": self._categorize(sat.name),
            })
            seen.add(norad)

        # 1. Exact NORAD ID
        try:
            norad_hit = int(q_lower)
        except ValueError:
            norad_hit = None
        if norad_hit is not None and norad_hit in self._index:
            _push(norad_hit)
            return {"query": q, "matches": matches, "total_found": 1, "showing": 1}

        # 2. Popular aliases (exact then substring)
        if q_lower in self._popular_aliases:
            _push(self._popular_aliases[q_lower])
        for alias, norad in self._popular_aliases.items():
            if len(matches) >= 20:
                break
            if q_lower in alias and self._popular_aliases.get(alias) not in seen:
                _push(norad)

        # 3. Substring match on actual TLE names
        for norad, sat in self._index.items():
            if q_lower in sat.name.lower():
                total += 1
                if len(matches) < 20 and norad not in seen:
                    _push(norad)

        # The total count reflects only TLE-name substring hits (the "+ N more"
        # affordance in the UI dropdown). Alias-only resolutions are surfaced
        # in `matches` but not counted in `total_found`.
        return {
            "query": q,
            "matches": matches,
            "total_found": max(total, len(matches)),
            "showing": len(matches),
        }

    # ------------------------------------------------------------------
    # Public API — full state
    # ------------------------------------------------------------------

    def get_state(self, norad_id: int) -> dict[str, Any] | None:
        """Compute live state for one satellite via SGP4."""
        try:
            norad = int(norad_id)
        except (TypeError, ValueError):
            return None

        sat = self._index.get(norad)
        if sat is None:
            return None

        now = self.ts.now()
        now_dt = now.utc_datetime()

        try:
            geocentric = sat.at(now)
            geo_pos = wgs84.geographic_position_of(geocentric)
        except Exception as exc:
            log.warning("[scan_signal] propagation failed for %s: %s", norad, exc)
            return None

        lat = float(geo_pos.latitude.degrees)
        lon = float(geo_pos.longitude.degrees)
        alt_km = float(geo_pos.elevation.km)

        velocity = geocentric.velocity.km_per_s  # numpy array (vx, vy, vz)
        speed_kms = float(math.sqrt(
            float(velocity[0]) ** 2
            + float(velocity[1]) ** 2
            + float(velocity[2]) ** 2
        ))

        # Orbital elements from sgp4 model
        no_kozai = float(sat.model.no_kozai)  # rev/min as radians/min
        period_min = (2.0 * math.pi / no_kozai) if no_kozai > 1e-9 else 0.0
        inclination_deg = float(sat.model.inclo) * 180.0 / math.pi
        eccentricity = float(sat.model.ecco)

        # TLE freshness
        try:
            epoch_dt = sat.epoch.utc_datetime()
            tle_age_days = (now_dt - epoch_dt).total_seconds() / 86400.0
        except Exception:
            tle_age_days = 0.0

        # Recent ground track — last 10 minutes (1 sample/min, going back)
        ground_track = []
        for delta_min in range(10, 0, -1):
            past = now_dt - timedelta(minutes=delta_min)
            t = self.ts.from_datetime(past.replace(tzinfo=timezone.utc))
            try:
                gp = wgs84.geographic_position_of(sat.at(t))
                ground_track.append([
                    round(float(gp.latitude.degrees), 4),
                    round(float(gp.longitude.degrees), 4),
                    past.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                ])
            except Exception:
                continue

        # Next pass over Tlemcen
        next_pass = self._compute_next_pass(sat, now)

        # Antenna reception across the ASTRO-SCAN observatories.
        # `in_sight_count` is the *unfiltered* number of observatories that
        # currently have the satellite above their local horizon — distinct
        # from `antenna_reception` (which is the top-N by RSSI for display).
        antenna_reception, in_sight_count = self._compute_antenna_reception(
            lat, lon, alt_km
        )
        total_obs = len(self._observatories)

        return {
            "norad_id": norad,
            "name": sat.name,
            "category": self._categorize(sat.name),
            "tle_age_days": round(tle_age_days, 2),
            "tle_source": "celestrak/satnogs",
            "position": {
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "altitude_km": round(alt_km, 1),
            },
            "velocity": {
                "kms": round(speed_kms, 2),
                "kmh": int(round(speed_kms * 3600)),
            },
            "orbit": {
                "period_minutes": round(period_min, 1),
                "inclination_deg": round(inclination_deg, 2),
                "eccentricity": round(eccentricity, 4),
            },
            "ground_track_recent": ground_track,
            "next_pass_tlemcen": next_pass,
            "antenna_reception": antenna_reception,
            "in_sight_count": in_sight_count,
            "observatories_total": total_obs,
            "computed_at": now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

    # ------------------------------------------------------------------
    # Public API — health
    # ------------------------------------------------------------------

    def get_health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._index else "degraded",
            "skyfield": "ok",
            "observatories": len(self._observatories),
            "tle_total": self._raw_count,
            "tle_loaded": self._fresh_count,
            "tle_obsolete_skipped": self._obsolete_count,
            "tle_age_avg_days": round(self._tle_age_avg_days, 1),
            "tle_oldest_fresh_days": round(self._tle_oldest_fresh_days, 1),
            "tle_path": self._tle_path,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _categorize(name: str) -> str:
        n = (name or "").upper()
        if "ISS" in n or "ZARYA" in n or "TIANGONG" in n or "TIANHE" in n:
            return "space_station"
        if "STARLINK" in n:
            return "starlink"
        if "ONEWEB" in n:
            return "oneweb"
        if "HUBBLE" in n or "HST" in n or "JWST" in n or "WEBB" in n or "TESS" in n:
            return "telescope"
        if "NOAA" in n or "GOES" in n or "METOP" in n or "METEOR" in n:
            return "weather"
        if "GPS" in n or "GLONASS" in n or "GALILEO" in n or "BEIDOU" in n or "NAVSTAR" in n:
            return "navigation"
        if "LANDSAT" in n or "SENTINEL" in n or "MODIS" in n or "TERRA" in n or "AQUA" in n:
            return "earth_observation"
        if "DEB" in n or "FRAG" in n or "R/B" in n:
            return "debris"
        if "COSMOS" in n or "USA " in n or "NROL" in n:
            return "military"
        return "satellite"

    def _compute_next_pass(self, sat: EarthSatellite, t_now) -> dict[str, Any] | None:
        """Find next pass with elevation >= 10° within the next 24h
        as seen from Tlemcen."""
        try:
            observer = wgs84.latlon(_TLEMCEN_LAT, _TLEMCEN_LON, _TLEMCEN_ELEV_M)
            t_end = self.ts.from_datetime(
                (t_now.utc_datetime() + timedelta(hours=24)).replace(tzinfo=timezone.utc)
            )
            t, events = sat.find_events(observer, t_now, t_end, altitude_degrees=10.0)
            n = len(events)
            for i in range(n):
                if int(events[i]) != 0:  # 0 = rise
                    continue
                rise_t = t[i]
                # Find subsequent set
                set_t = None
                culm_t = None
                for j in range(i + 1, n):
                    ev = int(events[j])
                    if ev == 1:
                        culm_t = t[j]
                    if ev == 2:
                        set_t = t[j]
                        break
                if set_t is None:
                    continue

                # Max elevation: prefer the culmination event Skyfield gave us
                if culm_t is None:
                    mid_dt = (
                        rise_t.utc_datetime()
                        + (set_t.utc_datetime() - rise_t.utc_datetime()) / 2
                    )
                    culm_t = self.ts.from_datetime(mid_dt.replace(tzinfo=timezone.utc))

                difference = sat - observer
                topocentric = difference.at(culm_t)
                alt, _az, _r = topocentric.altaz()
                duration_s = (set_t.utc_datetime() - rise_t.utc_datetime()).total_seconds()

                return {
                    "rise_time_utc": rise_t.utc_iso(),
                    "set_time_utc": set_t.utc_iso(),
                    "max_elevation_deg": round(float(alt.degrees), 1),
                    "duration_seconds": int(duration_s),
                }
            return None
        except Exception as exc:
            log.debug("[scan_signal] find_events failed: %s", exc)
            return None

    def _compute_antenna_reception(
        self, sat_lat: float, sat_lon: float, sat_alt_km: float
    ) -> tuple[list[dict[str, Any]], int]:
        """Compute reception per ASTRO-SCAN antenna.

        Returns ``(top_n, in_sight_count)`` where:
          * ``top_n`` is the top-N antennas above horizon ordered by RSSI desc
            (used by the HUD reception list)
          * ``in_sight_count`` is the total number of observatories with the
            satellite above their local horizon (used by the "X/12" badge)
        """
        if not self._observatories:
            return [], 0

        sat_alt_m = sat_alt_km * 1000.0
        results: list[dict[str, Any]] = []

        for obs in self._observatories:
            try:
                obs_lat = float(obs["lat"])
                obs_lon = float(obs["lon"])
                obs_elev_m = float(obs.get("elevation_m", 0))
            except (KeyError, TypeError, ValueError):
                continue

            ground_km = haversine_km(obs_lat, obs_lon, sat_lat, sat_lon)
            elev_deg = satellite_elevation_deg(
                obs_lat, obs_lon, obs_elev_m,
                sat_lat, sat_lon, sat_alt_m,
            )
            if elev_deg < _ANTENNA_MIN_ELEV:
                continue

            slant_km = slant_range_km(
                obs_lat, obs_lon, obs_elev_m,
                sat_lat, sat_lon, sat_alt_m,
            )
            freq_mhz = float(obs.get("frequency_mhz") or _ANTENNA_DEFAULT_FREQ_MHZ)
            rssi = rssi_estimate_dbm(slant_km, freq_mhz, _ANTENNA_DEFAULT_TX_DBM)

            if rssi >= -85.0:
                quality = "STRONG"
            elif rssi >= -95.0:
                quality = "GOOD"
            elif rssi >= -105.0:
                quality = "WEAK"
            else:
                quality = "MARGINAL"

            results.append({
                "antenna_id": obs.get("id"),
                "antenna_name": obs.get("name"),
                "antenna_lat": obs_lat,
                "antenna_lon": obs_lon,
                "ground_distance_km": round(ground_km, 1),
                "distance_km": round(slant_km, 1),
                "elevation_deg": round(elev_deg, 1),
                "rssi_dbm": round(rssi, 1),
                "quality": quality,
                "in_horizon": True,
                "frequency_mhz": round(freq_mhz, 3),
            })

        results.sort(key=lambda x: -x["rssi_dbm"])
        return results[:_ANTENNA_TOP_N], len(results)
