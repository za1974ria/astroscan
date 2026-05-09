"""Ground Assets — service layer.

Single entry point: GroundAssetsService.

Responsibilities:
  - Compose observatory state with day/night logic (solar altitude)
  - Drive mobile mission + balloon simulation
  - Compute antenna links and aggregate stats
  - Synthesise plausible mission-control events from current state
  - Cache the assembled network state in Redis (5 s TTL)
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any

from app.blueprints.ground_assets.data_sources import (
    compute_antenna_links,
    great_circle_km,
    load_observatories,
    simulate_balloons,
    simulate_missions,
    solar_altitude_deg,
)

log = logging.getLogger(__name__)

# Soft-import Redis cache. Falls back to compute-live if unavailable.
try:
    from app.utils.cache import cache_get, cache_set
    _CACHE_AVAILABLE = True
except Exception:  # pragma: no cover
    _CACHE_AVAILABLE = False
    log.warning("[ground_assets] cache layer unavailable — recompute on every call")

NETWORK_CACHE_KEY = "ground_assets:network"
NETWORK_CACHE_TTL = 5  # seconds — spec
EVENTS_CACHE_KEY = "ground_assets:events"
EVENTS_CACHE_TTL = 60


class GroundAssetsService:
    """Stateless service — safe to instantiate per-request."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_network_state(self) -> dict[str, Any]:
        """Returns the full network state, cached 5 s in Redis."""
        if _CACHE_AVAILABLE:
            cached = self._cache_get(NETWORK_CACHE_KEY)
            if cached is not None:
                return cached
        state = self._compute_network_state()
        if _CACHE_AVAILABLE:
            self._cache_set(NETWORK_CACHE_KEY, state, NETWORK_CACHE_TTL)
        return state

    def get_asset_detail(self, asset_id: str) -> dict[str, Any] | None:
        """Returns the detailed record for one asset (observatory / mission / balloon)."""
        state = self.get_network_state()
        for collection in ("observatories", "missions", "balloons"):
            for item in state.get(collection, []):
                if item.get("id") == asset_id:
                    detail = dict(item)
                    detail["last_contact_utc"] = state["timestamp"]
                    detail["antenna_links"] = [
                        link for link in state.get("antennas", [])
                        if link.get("target_id") == asset_id or link.get("obs_id") == asset_id
                    ]
                    return detail
        return None

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns the latest synthesised events. Cached so all workers agree."""
        if _CACHE_AVAILABLE:
            cached = self._cache_get(EVENTS_CACHE_KEY)
            if cached is not None:
                return cached[:limit]
        events = self._synthesise_events()
        if _CACHE_AVAILABLE:
            self._cache_set(EVENTS_CACHE_KEY, events, EVENTS_CACHE_TTL)
        return events[:limit]

    def get_health(self) -> dict[str, Any]:
        """Module health — coherent with /health pattern."""
        sources: dict[str, str] = {}
        try:
            obs = load_observatories()
            sources["observatories"] = f"ok ({len(obs)} sites)"
        except Exception as exc:
            sources["observatories"] = f"error: {exc}"
        try:
            simulate_missions(datetime.now(timezone.utc))
            sources["missions"] = "ok"
        except Exception as exc:
            sources["missions"] = f"error: {exc}"
        try:
            simulate_balloons(datetime.now(timezone.utc))
            sources["balloons"] = "ok"
        except Exception as exc:
            sources["balloons"] = f"error: {exc}"
        sources["redis_cache"] = "ok" if _CACHE_AVAILABLE else "degraded"
        degraded = any(v.startswith("error") for v in sources.values())
        return {
            "status": "degraded" if degraded else "ok",
            "data_sources": sources,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Private — composition
    # ------------------------------------------------------------------

    def _compute_network_state(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        observatories = self._compute_observatories(now)
        missions = simulate_missions(now)
        balloons = simulate_balloons(now)
        antennas = compute_antenna_links(observatories, missions + balloons)

        observed_targets = {l["target_id"] for l in antennas}

        stats = {
            "observatories_total": len(observatories),
            "observatories_online": sum(1 for o in observatories if o["status"] in ("observing", "online")),
            "missions_active": sum(1 for m in missions if m["status"] == "active"),
            "balloons_flying": sum(1 for b in balloons if b["status"] == "flying"),
            "links_active": len(antennas),
            "targets_tracked": len(observed_targets),
            # Cosmetic latency derived from now — stable for ~10s, plausible
            "network_latency_ms": 38 + (int(now.timestamp()) % 27),
        }

        return {
            "timestamp": now.isoformat(),
            "observatories": observatories,
            "missions": missions,
            "balloons": balloons,
            "antennas": antennas,
            "stats": stats,
        }

    def _compute_observatories(self, now: datetime) -> list[dict]:
        """Loads observatories and assigns status based on real solar altitude."""
        out: list[dict] = []
        for obs in load_observatories():
            try:
                alt = solar_altitude_deg(obs["lat"], obs["lon"], now)
            except Exception as exc:
                log.warning("[ground_assets] solar alt failed for %s: %s", obs["id"], exc)
                # Crude UTC fallback: night between 18:00 and 06:00 local
                local_hour = (now.hour + obs["lon"] / 15.0) % 24
                alt = -10.0 if (local_hour >= 18 or local_hour < 6) else 30.0
            obs["sun_altitude_deg"] = round(alt, 2)
            if alt < -6:
                obs["status"] = "observing"
                obs["status_label"] = "OBSERVING"
            elif alt < 0:
                obs["status"] = "online"
                obs["status_label"] = "TWILIGHT"
            elif alt < 10:
                obs["status"] = "standby"
                obs["status_label"] = "STANDBY"
            else:
                # Slightly randomised but deterministic per (id, hour)
                seed = abs(hash((obs["id"], now.strftime("%Y%m%d%H")))) % 100
                if seed < 12:
                    obs["status"] = "maintenance"
                    obs["status_label"] = "MAINTENANCE"
                else:
                    obs["status"] = "standby"
                    obs["status_label"] = "DAYLIGHT"
            # Compute distance to home (Tlemcen)
            obs["distance_from_home_km"] = round(
                great_circle_km(34.87, -1.32, obs["lat"], obs["lon"]), 0
            )
            out.append(obs)
        return out

    # ------------------------------------------------------------------
    # Private — events synthesis
    # ------------------------------------------------------------------

    def _synthesise_events(self) -> list[dict[str, Any]]:
        """Generates plausible recent mission-control events from current state."""
        state = self._compute_network_state()
        now = datetime.now(timezone.utc)
        rng = random.Random(int(now.timestamp()) // 30)  # stable per 30s bucket
        events: list[dict[str, Any]] = []

        # 1. Observatory acquisitions (most recent first)
        targets_pool = [
            "HD127334", "M51", "NGC4565", "Vega", "Betelgeuse", "TRAPPIST-1",
            "WASP-12b", "Sgr A*", "Crab Nebula", "Andromeda M31", "Orion Nebula",
        ]
        for o in state["observatories"]:
            if o["status"] == "observing":
                tgt = rng.choice(targets_pool)
                events.append({
                    "timestamp": now.isoformat(),
                    "source": o["id"].upper().replace("-", "_"),
                    "level": "info",
                    "message_en": f"Target {tgt} acquired — {o['telescope'].split(' ')[0]}",
                    "message_fr": f"Cible {tgt} acquise — {o['telescope'].split(' ')[0]}",
                })
            elif o["status"] == "standby":
                events.append({
                    "timestamp": now.isoformat(),
                    "source": o["id"].upper().replace("-", "_"),
                    "level": "info",
                    "message_en": f"Sun above horizon — standby ({o['sun_altitude_deg']:+.1f}°)",
                    "message_fr": f"Soleil au-dessus de l'horizon — veille ({o['sun_altitude_deg']:+.1f}°)",
                })
            elif o["status"] == "maintenance":
                events.append({
                    "timestamp": now.isoformat(),
                    "source": o["id"].upper().replace("-", "_"),
                    "level": "warn",
                    "message_en": f"Scheduled maintenance window — {o['name']}",
                    "message_fr": f"Fenêtre de maintenance — {o['name']}",
                })

        # 2. Mission GPS / beacon
        for m in state["missions"]:
            events.append({
                "timestamp": now.isoformat(),
                "source": m["callsign"],
                "level": "info",
                "message_en": (
                    f"GPS lock {m['lat']:+.3f}°, {m['lon']:+.3f}° — "
                    f"{m['speed_kmh']:.0f} km/h heading {m['heading_deg']:.0f}°"
                ),
                "message_fr": (
                    f"GPS verrouillé {m['lat']:+.3f}°, {m['lon']:+.3f}° — "
                    f"{m['speed_kmh']:.0f} km/h cap {m['heading_deg']:.0f}°"
                ),
            })

        # 3. Balloon altitude milestones
        for b in state["balloons"]:
            stage_msg = {
                "ascent": (
                    f"Ascent {b['altitude_m']:.0f} m — climb {b['vertical_speed_ms']:+.1f} m/s",
                    f"Ascension {b['altitude_m']:.0f} m — montée {b['vertical_speed_ms']:+.1f} m/s",
                ),
                "float": (
                    f"Plateau reached {b['altitude_m']:.0f} m — drifting",
                    f"Plateau atteint {b['altitude_m']:.0f} m — dérive",
                ),
                "burst": (
                    f"Burst event — descent {b['vertical_speed_ms']:.1f} m/s",
                    f"Éclatement — descente {b['vertical_speed_ms']:.1f} m/s",
                ),
                "descent": (
                    f"Parachute descent {b['altitude_m']:.0f} m",
                    f"Descente sous parachute {b['altitude_m']:.0f} m",
                ),
            }
            en, fr = stage_msg.get(b["stage"], ("Telemetry update", "Mise à jour télémétrie"))
            events.append({
                "timestamp": now.isoformat(),
                "source": b["callsign"],
                "level": "warn" if b["stage"] == "burst" else "info",
                "message_en": en,
                "message_fr": fr,
            })

        # 4. Antenna link RSSI updates (top 5)
        for link in state["antennas"][:5]:
            events.append({
                "timestamp": now.isoformat(),
                "source": link["obs_id"].upper().replace("-", "_"),
                "level": "info",
                "message_en": (
                    f"Tracking {link['target_id']} — "
                    f"RSSI {link['rssi_dbm']:+.0f} dBm @ {link['distance_km']:.0f} km"
                ),
                "message_fr": (
                    f"Suivi {link['target_id']} — "
                    f"RSSI {link['rssi_dbm']:+.0f} dBm à {link['distance_km']:.0f} km"
                ),
            })

        # Apply a synthetic age to each event so the stream feels alive: most
        # recent first, spaced 4–18 s apart, deterministic from the bucket.
        spaced: list[dict[str, Any]] = []
        cursor = int(now.timestamp())
        for ev in events:
            cursor -= 4 + rng.randint(0, 14)
            ev["timestamp"] = datetime.fromtimestamp(cursor, tz=timezone.utc).isoformat()
            spaced.append(ev)
        return spaced

    # ------------------------------------------------------------------
    # Cache helpers (graceful fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_get(key: str) -> Any | None:
        try:
            return cache_get(key, 0)
        except Exception as exc:
            log.warning("[ground_assets] cache_get %s failed: %s", key, exc)
            return None

    @staticmethod
    def _cache_set(key: str, value: Any, ttl: int) -> None:
        try:
            cache_set(key, value, ttl)
        except Exception as exc:
            log.warning("[ground_assets] cache_set %s failed: %s", key, exc)
