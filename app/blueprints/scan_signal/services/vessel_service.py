"""SCAN A SIGNAL — vessel tracking service.

Reads vessels stored by AISStreamSubscriber from Redis and computes:
  • the ASTRO-SCAN antenna reception model (per-observatory distance,
    RSSI, quality bucket) using marine VHF AIS channel as reference,
  • a set of premium enrichments (flag, sea zone, declared destination,
    movement provenance, tracking duration) — all derived locally from
    static dictionaries (no external API).

VHF AIS coastal range is typically 30–60 km; we use an 80 km cutoff for
display purposes (an antenna further than that is dropped from the list).
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from typing import Any

from app.blueprints.scan_signal.services.radio_propagation import (
    haversine_km,
    rssi_estimate_dbm,
)
from app.blueprints.scan_signal.services.vessel_enrichment import (
    country_by_iso,
    detect_inland_waterway,
    format_duration,
    geocode_sea_zone,
    is_invalid_ais_value,
    mid_to_country,
    parse_destination,
)

log = logging.getLogger(__name__)

# AIS Marine VHF channels: 161.975 MHz (AIS 1) and 162.025 MHz (AIS 2).
_AIS_FREQ_MHZ = 162.0

# Effective Isotropic Radiated Power (dBm) — typical merchant vessel AIS
# transmitter is 12.5 W ≈ 41 dBm. 36 dBm is a conservative Class A/B mix.
_AIS_TX_DBM = 36.0

# Coastal AIS reception cutoff (km).
_AIS_RANGE_KM = 80.0

_OBSERVATORIES_PATH = "/root/astro_scan/app/blueprints/ground_assets/observatories.json"

_REDIS_KEY_VESSELS = "as:scan:vessels"
_REDIS_KEY_BY_NAME = "as:scan:vessels_by_name"
_REDIS_KEY_STATIC = "as:scan:vessels_static"
_REDIS_KEY_HISTORY_PREFIX = "as:scan:vessels_history:"
_REDIS_KEY_FIRST_SEEN = "as:scan:vessels_first_seen"

# Numeric AIS NavigationalStatus → human readable bucket
_NAV_STATUS_LABELS = {
    0: "underway",
    1: "anchored",
    2: "not_under_command",
    3: "restricted_maneuverability",
    4: "constrained_draught",
    5: "moored",
    6: "aground",
    7: "fishing",
    8: "underway_sailing",
    15: "undefined",
}


class VesselService:
    """Vessel lookup + reception modelling backed by the AISStream Redis cache."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self._observatories: list[dict] = []
        self._load_observatories()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _load_observatories(self) -> None:
        try:
            with open(_OBSERVATORIES_PATH, "r", encoding="utf-8") as f:
                self._observatories = json.load(f)
            log.info("[vessel_service] loaded %d observatories", len(self._observatories))
        except Exception as exc:
            log.warning("[vessel_service] failed to load observatories: %s", exc)
            self._observatories = []

    # ------------------------------------------------------------------
    # Public API — search
    # ------------------------------------------------------------------

    def search(self, query: str) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {"query": "", "matches": [], "total_found": 0, "showing": 0}

        q_upper = q.upper()
        matches: list[dict] = []
        seen: set[str] = set()

        if self.redis is None:
            return {"query": q, "matches": [], "total_found": 0, "showing": 0}

        if q.isdigit():
            try:
                raw = self.redis.hget(_REDIS_KEY_VESSELS, q)
            except Exception:
                raw = None
            if raw:
                try:
                    v = json.loads(raw)
                    matches.append(self._brief(v))
                    seen.add(str(v.get("mmsi")))
                except Exception:
                    pass

        try:
            mmsi_by_name = self.redis.hget(_REDIS_KEY_BY_NAME, q_upper)
        except Exception:
            mmsi_by_name = None
        if mmsi_by_name and mmsi_by_name not in seen:
            try:
                raw = self.redis.hget(_REDIS_KEY_VESSELS, mmsi_by_name)
                if raw:
                    v = json.loads(raw)
                    matches.append(self._brief(v))
                    seen.add(str(v.get("mmsi")))
            except Exception:
                pass

        try:
            all_names = self.redis.hkeys(_REDIS_KEY_BY_NAME)
        except Exception:
            all_names = []

        total = 0
        for name in all_names:
            if q_upper in name:
                total += 1
                if len(matches) >= 20:
                    continue
                try:
                    mmsi = self.redis.hget(_REDIS_KEY_BY_NAME, name)
                    if not mmsi or mmsi in seen:
                        continue
                    raw = self.redis.hget(_REDIS_KEY_VESSELS, mmsi)
                    if not raw:
                        continue
                    v = json.loads(raw)
                    matches.append(self._brief(v))
                    seen.add(str(v.get("mmsi")))
                except Exception:
                    continue

        return {
            "query": q,
            "matches": matches,
            "total_found": max(total, len(matches)),
            "showing": len(matches),
        }

    # ------------------------------------------------------------------
    # Public API — full vessel state (with enrichments)
    # ------------------------------------------------------------------

    def get_state(self, mmsi: str | int, lang: str = "fr") -> dict[str, Any] | None:
        try:
            mmsi_str = str(int(mmsi))
        except (TypeError, ValueError):
            return None

        if self.redis is None:
            return None

        try:
            raw = self.redis.hget(_REDIS_KEY_VESSELS, mmsi_str)
        except Exception:
            return None
        if not raw:
            return None

        try:
            v = json.loads(raw)
        except Exception:
            return None

        try:
            lat = float(v.get("latitude"))
            lon = float(v.get("longitude"))
        except (TypeError, ValueError):
            return None

        # AIS sentinel cleanup --------------------------------------------------
        sog = v.get("sog_knots")
        if is_invalid_ais_value(sog, "sog"):
            sog = None
        cog = v.get("cog_deg")
        if is_invalid_ais_value(cog, "cog"):
            cog = None
        heading = v.get("true_heading_deg")
        if is_invalid_ais_value(heading, "heading"):
            heading = None

        antenna_reception, in_sight_count = self._compute_antenna_reception(lat, lon)

        nav_status_raw = v.get("nav_status")
        nav_status_label = _NAV_STATUS_LABELS.get(
            nav_status_raw if isinstance(nav_status_raw, int) else -1
        )

        # Enrichment 1 — Flag (pavillon) ---------------------------------------
        flag = mid_to_country(mmsi_str)

        # Enrichment 2 — Current sea zone --------------------------------------
        sea_zone = geocode_sea_zone(lat, lon, lang)

        # Enrichment 2.5 — Inland waterway honesty disclosure ------------------
        # Many AIS positions for European ports (Antwerp/Rotterdam/Hamburg…)
        # sit dozens of km up a river and appear "on land" at world zoom.
        inland_waterway = detect_inland_waterway(lat, lon, lang)

        # Enrichment 3 — Declared destination (Type 5) -------------------------
        destination = self._destination(mmsi_str, lang)

        # Enrichment 4 — Provenance (history reverse-geocode) ------------------
        provenance = self._provenance(mmsi_str, lang)

        # Enrichment 5 — Tracking duration -------------------------------------
        tracking_duration = self._tracking_duration(mmsi_str, lang)

        # Enrichment side-data — static record (length, IMO, callsign, etc.)
        static_extras = self._static_extras(mmsi_str)

        # Pick the best name available: live PositionReport → static Type 5 →
        # MMSI fallback.
        name = (v.get("name") or "").strip() or (static_extras.get("name") or "").strip()
        if not name:
            name = f"MMSI {mmsi_str}"

        return {
            "mmsi": mmsi_str,
            "name": name,
            "category": "vessel",
            "position": {
                "latitude": round(lat, 5),
                "longitude": round(lon, 5),
            },
            "kinematics": {
                "sog_knots": _round_or_none(sog, 1),
                "cog_deg": _round_or_none(cog, 1),
                "true_heading_deg": _round_or_none(heading, 0),
            },
            "nav_status": {
                "code": nav_status_raw,
                "label": nav_status_label,
            },
            # New enrichments ----------------------------------------------------
            "flag": flag,
            "sea_zone": sea_zone,
            "inland_waterway": inland_waterway,
            "destination": destination,
            "provenance": provenance,
            "tracking_duration": tracking_duration,
            "static": static_extras or None,
            # Existing reception model ------------------------------------------
            "antenna_reception": antenna_reception,
            "in_sight_count": in_sight_count,
            "observatories_total": len(self._observatories),
            "timestamp": v.get("timestamp"),
            "source": "AISStream PositionReport + ShipStaticData",
        }

    # ------------------------------------------------------------------
    # Enrichment helpers
    # ------------------------------------------------------------------

    def _destination(self, mmsi: str, lang: str) -> dict[str, Any] | None:
        try:
            raw = self.redis.hget(_REDIS_KEY_STATIC, mmsi)
        except Exception:
            return None
        if not raw:
            return None
        try:
            static = json.loads(raw)
        except Exception:
            return None

        dest = parse_destination(static.get("destination"))
        if not dest:
            return None

        country_iso = dest.get("country_iso")
        if country_iso:
            country = country_by_iso(country_iso)
            if country:
                dest["flag"] = country.get("flag")
                dest["country_name"] = (
                    country.get("name_fr") if lang == "fr" else country.get("name_en")
                )

        eta = static.get("eta")
        if isinstance(eta, dict):
            dest["eta"] = self._format_eta(eta, lang)
        return dest

    @staticmethod
    def _format_eta(eta: dict, lang: str) -> str | None:
        try:
            month = int(eta.get("Month") or 0)
            day = int(eta.get("Day") or 0)
            hour = int(eta.get("Hour") or 0)
            minute = int(eta.get("Minute") or 0)
        except (TypeError, ValueError):
            return None
        if month == 0 or day == 0:
            return None
        # AIS ETA has no year; use the next occurrence of (month, day) from now.
        return f"{day:02d}/{month:02d} {hour:02d}:{minute:02d} UTC"

    def _provenance(self, mmsi: str, lang: str) -> dict[str, Any] | None:
        key = _REDIS_KEY_HISTORY_PREFIX + mmsi
        try:
            entries = self.redis.lrange(key, 0, -1)
        except Exception:
            return None
        if not entries:
            return None

        # Oldest = last element (we LPUSH freshest first)
        try:
            oldest_raw = entries[-1]
            oldest = json.loads(oldest_raw)
            old_lat = float(oldest.get("lat"))
            old_lon = float(oldest.get("lon"))
            old_ts_raw = oldest.get("ts")
            old_ts = datetime.fromisoformat(old_ts_raw.replace("Z", "+00:00"))
            if old_ts.tzinfo is None:
                old_ts = old_ts.replace(tzinfo=timezone.utc)
        except Exception:
            return None

        now = datetime.now(timezone.utc)
        age_hours = (now - old_ts).total_seconds() / 3600.0
        if age_hours < 1.0:
            # not enough history yet
            return {"hours_ago": round(age_hours, 1), "zone": None, "fresh": True}

        old_zone = geocode_sea_zone(old_lat, old_lon, lang)
        return {
            "hours_ago": round(age_hours, 1),
            "zone": old_zone,
            "lat": round(old_lat, 4),
            "lon": round(old_lon, 4),
            "fresh": False,
            "samples": len(entries),
        }

    def _tracking_duration(self, mmsi: str, lang: str) -> dict[str, Any] | None:
        try:
            first_seen_raw = self.redis.hget(_REDIS_KEY_FIRST_SEEN, mmsi)
        except Exception:
            return None
        if not first_seen_raw:
            return None
        try:
            if isinstance(first_seen_raw, bytes):
                first_seen_raw = first_seen_raw.decode()
            first_seen = datetime.fromisoformat(first_seen_raw.replace("Z", "+00:00"))
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=timezone.utc)
        except Exception:
            return None

        duration_sec = (datetime.now(timezone.utc) - first_seen).total_seconds()
        if duration_sec < 0:
            duration_sec = 0
        return {
            "seconds": int(duration_sec),
            "human": format_duration(duration_sec, lang),
            "first_seen": first_seen_raw,
        }

    def _static_extras(self, mmsi: str) -> dict[str, Any]:
        try:
            raw = self.redis.hget(_REDIS_KEY_STATIC, mmsi)
        except Exception:
            return {}
        if not raw:
            return {}
        try:
            static = json.loads(raw)
        except Exception:
            return {}
        # Don't include destination / eta here — they're already exposed via
        # the dedicated `destination` field. Just surface static identity bits.
        out = {
            "name": static.get("name"),
            "callsign": static.get("callsign"),
            "imo": static.get("imo"),
            "ship_type": static.get("ship_type"),
            "length_m": static.get("length"),
            "breadth_m": static.get("breadth"),
            "max_static_draught_m": static.get("max_static_draught"),
            "updated_at": static.get("updated_at"),
        }
        # Drop empties so the payload stays tidy
        return {k: v for k, v in out.items() if v not in (None, "", 0)}

    # ------------------------------------------------------------------
    # Public API — historical track (for trail rendering)
    # ------------------------------------------------------------------

    def get_track(self, mmsi: str | int, limit: int = 10) -> list[dict[str, Any]]:
        """Return last `limit` historical positions, oldest-first.

        The subscriber stores history with LPUSH (newest at index 0),
        so we slice [0:limit] then reverse for oldest→newest rendering.
        """
        try:
            mmsi_str = str(int(mmsi))
        except (TypeError, ValueError):
            return []
        if self.redis is None:
            return []
        key = _REDIS_KEY_HISTORY_PREFIX + mmsi_str
        try:
            entries = self.redis.lrange(key, 0, max(0, int(limit) - 1))
        except Exception:
            return []
        if not entries:
            return []

        track: list[dict[str, Any]] = []
        for raw in entries:
            try:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                entry = json.loads(raw)
                track.append({
                    "lat": float(entry.get("lat")),
                    "lon": float(entry.get("lon")),
                    "ts": entry.get("ts"),
                })
            except Exception:
                continue
        # Oldest first for trail rendering (gradient opacity ramp)
        track.reverse()
        return track

    # ------------------------------------------------------------------
    # Public API — recent vessels (for the popular grid)
    # ------------------------------------------------------------------

    def recent(self, limit: int = 20) -> dict[str, Any]:
        if self.redis is None:
            return {"items": [], "cache_size": 0}

        try:
            keys = self.redis.hkeys(_REDIS_KEY_VESSELS)
        except Exception:
            keys = []

        if not keys:
            return {"items": [], "cache_size": 0}

        sample = random.sample(keys, min(limit, len(keys)))
        items: list[dict] = []
        try:
            raws = self.redis.hmget(_REDIS_KEY_VESSELS, sample)
        except Exception:
            raws = []

        for raw in raws or []:
            if not raw:
                continue
            try:
                v = json.loads(raw)
                items.append(self._brief(v))
            except Exception:
                continue

        items.sort(key=lambda it: it.get("name") or it.get("mmsi") or "")
        return {"items": items, "cache_size": len(keys)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _brief(v: dict) -> dict:
        mmsi = str(v.get("mmsi") or "")
        flag = mid_to_country(mmsi)
        return {
            "mmsi": mmsi,
            "name": v.get("name") or f"MMSI {mmsi}",
            "latitude": v.get("latitude"),
            "longitude": v.get("longitude"),
            "sog_knots": v.get("sog_knots"),
            "flag": flag,
        }

    def _compute_antenna_reception(
        self, vessel_lat: float, vessel_lon: float
    ) -> tuple[list[dict[str, Any]], int]:
        if not self._observatories:
            return [], 0

        results: list[dict[str, Any]] = []
        for obs in self._observatories:
            try:
                obs_lat = float(obs["lat"])
                obs_lon = float(obs["lon"])
            except (KeyError, TypeError, ValueError):
                continue

            dist_km = haversine_km(obs_lat, obs_lon, vessel_lat, vessel_lon)
            if dist_km > _AIS_RANGE_KM:
                continue

            rssi = rssi_estimate_dbm(dist_km, _AIS_FREQ_MHZ, _AIS_TX_DBM)
            if rssi >= -75.0:
                quality = "STRONG"
            elif rssi >= -85.0:
                quality = "GOOD"
            elif rssi >= -95.0:
                quality = "WEAK"
            else:
                quality = "MARGINAL"

            results.append({
                "antenna_id": obs.get("id"),
                "antenna_name": obs.get("name"),
                "antenna_lat": obs_lat,
                "antenna_lon": obs_lon,
                "distance_km": round(dist_km, 1),
                "rssi_dbm": round(rssi, 1),
                "quality": quality,
                "frequency_mhz": _AIS_FREQ_MHZ,
            })

        results.sort(key=lambda x: -x["rssi_dbm"])
        return results[:5], len(results)


def _round_or_none(value: Any, decimals: int) -> Any:
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None
