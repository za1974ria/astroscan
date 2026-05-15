"""Zero-knowledge GeoIP country counter for Sentinel.

PRIVACY POSTURE — non-negotiable, baked into every method:

  - IP addresses are resolved IN MEMORY ONLY.
  - IPs are NEVER persisted (no DB, no log, no file, no exception payload).
  - The only datum stored is the ISO 3166-1 alpha-2 country code (2 chars).
  - Counters are aggregated and have NO link to a session, cookie, token,
    or precise timestamp. Only first_seen_day / last_seen_day (YYYY-MM-DD).
  - Private / loopback / link-local IPs and any lookup failure resolve
    to the sentinel value ``"XX"`` — never raised, never logged with the IP.

Conformity: GDPR Article 89 (aggregated statistical processing, no PII).

Performance: the MaxMind reader is opened ONCE at module import; access
is wrapped in a lock because the geoip2 Reader is not officially declared
thread-safe for concurrent ``country()`` calls — the lock is cheap (the
mmap-backed lookup is microseconds) and removes any risk under gunicorn's
threaded worker model.

Fail-safe: if the database file is missing or corrupted, the singleton
boots in DEGRADED mode and every ``resolve_country()`` returns ``"XX"``.
No exception ever escapes a public method of this module.
"""
from __future__ import annotations

import ipaddress
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional

try:
    import geoip2.database
    import geoip2.errors
    _GEOIP2_AVAILABLE = True
except Exception:  # pragma: no cover — defensive only
    _GEOIP2_AVAILABLE = False

_log = logging.getLogger("astroscan.sentinel.geoip")

_MMDB_PATH = "/root/astro_scan/data/geoip/GeoLite2-Country.mmdb"
_UNKNOWN = "XX"
_PRIVACY_NOTE = (
    "Zero-knowledge analytics. IP addresses are resolved in memory and "
    "never persisted. Only ISO 3166-1 alpha-2 country codes are stored, "
    "aggregated, with no link to any session, token, or precise time. "
    "Conforms to GDPR Article 89 (statistical processing)."
)


class GeoIPCounter:
    """Module-level singleton (see ``_INSTANCE`` below).

    Public surface:
      - ``resolve_country(ip)``  → 2-char ISO code or ``"XX"``
      - ``increment_counter(country_iso2, conn)``  → updates aggregate row
      - ``get_stats()``  → dict ready to expose on a public dashboard
    """

    def __init__(self, mmdb_path: str = _MMDB_PATH) -> None:
        self._reader = None
        self._lock = threading.Lock()
        self._degraded = True
        self._mmdb_path = mmdb_path
        if not _GEOIP2_AVAILABLE:
            _log.warning(
                "geoip2 library unavailable — GeoIPCounter in degraded mode"
            )
            return
        try:
            self._reader = geoip2.database.Reader(mmdb_path)
            self._degraded = False
            _log.info("GeoIPCounter ready (mmdb=%s)", mmdb_path)
        except FileNotFoundError:
            _log.warning(
                "GeoLite2 mmdb not found at %s — degraded mode", mmdb_path
            )
        except Exception as e:
            # Never log the IP, never propagate — degraded mode only.
            _log.warning(
                "GeoLite2 mmdb open failed (%s) — degraded mode",
                type(e).__name__,
            )

    # ─────────────────────────────────────────────── resolution
    def resolve_country(self, ip: str) -> str:
        """Resolve ``ip`` to ISO 3166-1 alpha-2. Returns ``"XX"`` on any
        failure or private/loopback address. The IP is never logged.
        """
        if self._degraded or self._reader is None:
            return _UNKNOWN
        if not ip:
            return _UNKNOWN
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            return _UNKNOWN
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            return _UNKNOWN
        try:
            with self._lock:
                resp = self._reader.country(ip)
            iso = (resp.country.iso_code or "").strip().upper()
            if len(iso) != 2 or not iso.isalpha():
                return _UNKNOWN
            return iso
        except Exception:
            # Catches AddressNotFoundError + any reader-level corruption.
            # The IP must not appear in the log line.
            return _UNKNOWN

    # ─────────────────────────────────────────────── persistence
    def increment_counter(
        self, country_iso2: str, conn: sqlite3.Connection
    ) -> None:
        """Atomically bump the aggregate row for ``country_iso2``.

        ``conn`` is a caller-managed SQLite connection (auto-commit
        isolation_level=None, which matches Sentinel's ``_connect()``).
        """
        if not country_iso2 or len(country_iso2) != 2:
            country_iso2 = _UNKNOWN
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            conn.execute(
                """
                INSERT INTO sentinel_country_counters
                    (country_iso2, count, first_seen_day, last_seen_day)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(country_iso2) DO UPDATE SET
                    count = count + 1,
                    last_seen_day = excluded.last_seen_day
                """,
                (country_iso2, today, today),
            )
        except sqlite3.Error as e:
            _log.warning(
                "sentinel_country_counters upsert failed (%s)",
                type(e).__name__,
            )

    # ─────────────────────────────────────────────── readout
    def get_stats(self) -> dict:
        """Public aggregate view. Never includes any PII."""
        by_country: dict = {}
        total = 0
        last_updated: Optional[str] = None
        try:
            # Use a short-lived read connection — does not depend on store.
            from app.blueprints.sentinel.store import _connect, init_schema
            init_schema()
            with _connect() as conn:
                rows = conn.execute(
                    "SELECT country_iso2, count, first_seen_day, last_seen_day "
                    "FROM sentinel_country_counters"
                ).fetchall()
            for r in rows:
                iso = r["country_iso2"]
                cnt = int(r["count"] or 0)
                by_country[iso] = {
                    "count": cnt,
                    "first_seen_day": r["first_seen_day"],
                    "last_seen_day": r["last_seen_day"],
                }
                total += cnt
                if last_updated is None or (
                    r["last_seen_day"] and r["last_seen_day"] > last_updated
                ):
                    last_updated = r["last_seen_day"]
        except Exception as e:
            _log.warning(
                "get_stats read failed (%s)", type(e).__name__
            )
        return {
            "total_sessions_lifetime": total,
            "by_country": by_country,
            "last_updated": last_updated,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "degraded": self._degraded,
            "privacy_note": _PRIVACY_NOTE,
        }


# Module-level singleton: built once at import. A failure here would only
# put the counter into degraded mode — it never raises.
_INSTANCE = GeoIPCounter()


def get_geoip_counter() -> GeoIPCounter:
    """Return the module-level singleton. Always non-None."""
    return _INSTANCE


# Defensive: surface a tiny health probe usable from tests.
def _self_check() -> dict:  # pragma: no cover
    inst = get_geoip_counter()
    return {
        "degraded": inst._degraded,
        "mmdb": inst._mmdb_path,
        "ts": int(time.time()),
    }
