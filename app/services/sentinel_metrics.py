"""Sentinel trust metrics — SQL-FIRST, fail-safe, read-only.

PHASE 3 (2026-05-23) — Source of truth for the trust block.

DESIGN DECISIONS (validated 2026-05-23):
    * SQL-FIRST HYBRID — sentinel_sessions is the source of truth.
      sentinel_metrics table exists as an OPTIONAL cache (key/value)
      but is NOT used as primary source. Reads always hit sentinel_sessions
      directly via SQL COUNT — no race conditions, no drift, no manual
      counter increments.
    * NO MANUAL HOOKS — the `increment_total_sessions` / `increment_completed_sessions`
      helpers exist (per brief) but are intentionally NO-OP (debug log only).
      Callers should not rely on them; metrics derive from sessions table.
    * FAIL-SAFE — every read function returns a safe default (0 or 0.0) if
      the database is unavailable, schema is missing, or any other error
      occurs. The UI must never crash because of metrics.
    * READ-ONLY — no writes to sentinel_metrics. No mutations to
      sentinel_sessions. No side effects.

Public API:
    get_total_sessions()       -> int
    get_completed_sessions()   -> int   (ENDED only — honest semantics)
    get_pending_sessions()     -> int   (PENDING_DRIVER | PENDING_PARENT)
    get_interrupted_sessions() -> int
    get_active_sessions()      -> int
    get_feedback_average()     -> float (0.0–5.0)
    get_feedback_count()       -> int
    get_metrics_snapshot()     -> dict      (one-shot all-in-one for the API)
    increment_total_sessions()     -> None  (NO-OP — debug log)
    increment_completed_sessions() -> None  (NO-OP — debug log)

The "active sessions" definition uses the LIVE states from
``app.blueprints.sentinel.state_machine``:
    ACTIVE, STOP_PENDING_PARENT, STOP_PENDING_DRIVER
AND ``expires_at > now`` (filter out forgotten / expired but not garbage-collected).
"""
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

log = logging.getLogger(__name__)


# Internal helpers ---------------------------------------------------------


def _db_path() -> str:
    """Resolve the SQLite path. Lazy import to avoid cycles at module load."""
    try:
        from app.services.paths import DB_PATH
        return DB_PATH
    except Exception:
        # Fallback if app.services.paths is unavailable (CI, tests).
        import os
        return os.environ.get("DB_PATH") or os.environ.get(
            "ASTROSCAN_DB_PATH", ""
        )


def _connect_ro() -> sqlite3.Connection | None:
    """Open a read-only connection with a short timeout.

    Returns None on any error — caller must handle the None.
    """
    try:
        path = _db_path()
        if not path:
            return None
        # mode=ro + nolock for cheapest possible read.
        conn = sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, timeout=2.0,
        )
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as exc:  # noqa: BLE001
        log.debug("[sentinel_metrics] connect failed: %s", exc)
        return None


def _safe_scalar(query: str, default: Any, params: tuple = ()) -> Any:
    """Run a 1-row 1-col SELECT and return its value, or default on any error.

    Never raises. Schema-missing, lock contention, file-missing, parse
    error → all collapse to `default`.
    """
    conn = _connect_ro()
    if conn is None:
        return default
    try:
        row = conn.execute(query, params).fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]
    except sqlite3.OperationalError as exc:
        # Most common: "no such table" — schema not initialized yet.
        log.debug("[sentinel_metrics] query soft-fail: %s", exc)
        return default
    except Exception as exc:  # noqa: BLE001
        log.debug("[sentinel_metrics] query unexpected: %s", exc)
        return default
    finally:
        try:
            conn.close()
        except Exception:
            pass


# Public API — sessions ---------------------------------------------------


def get_total_sessions() -> int:
    """Total sessions ever created (any state)."""
    val = _safe_scalar("SELECT COUNT(*) FROM sentinel_sessions", 0)
    try:
        return int(val)
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────
# HONEST METRICS (2026-05-29) — reverts the 2026-05-23 "PROTECTED"
# semantic which collapsed PENDING into completed_sessions and reported
# success_rate=100% even when every session was PENDING_DRIVER and had
# never been accepted by a driver. The states below mean exactly what
# they say:
#   COMPLETED   = sessions that actually ran to term (driver accepted,
#                 parent confirmed, ride finished cleanly) — ENDED only.
#   PENDING     = sessions waiting on a counter-party (driver or parent)
#                 to accept. They are NOT protected and NOT completed.
#   ACTIVE      = live, in-progress sessions (computed elsewhere, with
#                 expires_at filter — see get_active_sessions).
#   INTERRUPTED = sessions that died before completion (expired TTL,
#                 one-sided STOP confirmations, explicit failures).
# ─────────────────────────────────────────────────────────────────────

COMPLETED_STATES = ("ENDED",)

PENDING_STATES = (
    "PENDING_DRIVER",
    "PENDING_PARENT",
)

INTERRUPTED_STATES = (
    "EXPIRED",
    "STOP_PENDING_PARENT",
    "STOP_PENDING_DRIVER",
    "FAILED",
)


def _states_placeholder(states: tuple[str, ...]) -> str:
    """Return a SQL IN-clause placeholder ('?,?,?') for parameterised queries."""
    return ",".join(["?"] * len(states))


def get_completed_sessions() -> int:
    """Sessions actually run to term — state == 'ENDED' only.

    HONEST REDESIGN (2026-05-29): PENDING/ACTIVE are NOT counted as
    completed. A session that no driver ever accepted (started_at=0,
    driver_consent_at=0) is not a completed safety session — it never
    happened.
    """
    val = _safe_scalar(
        "SELECT COUNT(*) FROM sentinel_sessions "
        "WHERE state IN (" + _states_placeholder(COMPLETED_STATES) + ")",
        0,
        COMPLETED_STATES,
    )
    try:
        return int(val)
    except Exception:
        return 0


def get_pending_sessions() -> int:
    """Sessions waiting on driver or parent acceptance — not yet protected.

    state ∈ {PENDING_DRIVER, PENDING_PARENT}. These are explicitly NOT
    completed and NOT active; surfaced as a distinct KPI so the trust
    block can show them honestly instead of inflating success_rate.
    """
    val = _safe_scalar(
        "SELECT COUNT(*) FROM sentinel_sessions "
        "WHERE state IN (" + _states_placeholder(PENDING_STATES) + ")",
        0,
        PENDING_STATES,
    )
    try:
        return int(val)
    except Exception:
        return 0


def get_protected_sessions() -> int:
    """Back-compat alias — now equal to completed (ENDED only).

    Kept so older callers do not break. The previous semantics
    (ACTIVE+PENDING+ENDED) were dropped because they hid the fact
    that no driver had ever accepted a single session.
    """
    return get_completed_sessions()


def get_interrupted_sessions() -> int:
    """Sessions that died before completion.

    state ∈ INTERRUPTED_STATES:
        EXPIRED             : TTL auto-kill
        STOP_PENDING_PARENT : driver requested stop, parent never confirmed
        STOP_PENDING_DRIVER : parent requested stop, driver never confirmed
        FAILED              : reserved for future explicit-failure state
    """
    val = _safe_scalar(
        "SELECT COUNT(*) FROM sentinel_sessions "
        "WHERE state IN (" + _states_placeholder(INTERRUPTED_STATES) + ")",
        0,
        INTERRUPTED_STATES,
    )
    try:
        return int(val)
    except Exception:
        return 0


def get_active_sessions() -> int:
    """Sessions currently live (ACTIVE / STOP_PENDING_*) AND not expired.

    Definition uses LIVE states from state_machine.py + expires_at > now.
    """
    now_ts = int(time.time())
    val = _safe_scalar(
        "SELECT COUNT(*) FROM sentinel_sessions "
        "WHERE state IN ('ACTIVE', 'STOP_PENDING_PARENT', 'STOP_PENDING_DRIVER') "
        "AND expires_at > ?",
        0,
        (now_ts,),
    )
    try:
        return int(val)
    except Exception:
        return 0


# Public API — feedback --------------------------------------------------


def get_feedback_count() -> int:
    """Total number of feedback submissions (any status)."""
    val = _safe_scalar("SELECT COUNT(*) FROM sentinel_feedback", 0)
    try:
        return int(val)
    except Exception:
        return 0


def get_feedback_average() -> float:
    """Average rating (1.0 to 5.0) across all submitted feedback.

    Returns 0.0 if no feedback yet — UI handles by showing "—" or hiding
    the SATISFACTION card on first deploy.
    """
    val = _safe_scalar("SELECT AVG(rating) FROM sentinel_feedback", 0.0)
    try:
        return round(float(val), 2)
    except Exception:
        return 0.0


# Public API — countries (zero-knowledge geoip aggregate, no IP) ----------


# ISO 3166-1 alpha-2 → display name (French). XX is the standard "unknown".
# Extended on demand; unknown codes fall back to the ISO code uppercased.
_ISO_TO_NAME_FR: dict[str, str] = {
    "DZ": "Algérie", "FR": "France", "CA": "Canada", "US": "États-Unis",
    "BE": "Belgique", "CH": "Suisse", "MA": "Maroc", "TN": "Tunisie",
    "DE": "Allemagne", "ES": "Espagne", "IT": "Italie", "GB": "Royaume-Uni",
    "PT": "Portugal", "NL": "Pays-Bas", "LU": "Luxembourg", "SE": "Suède",
    "NO": "Norvège", "FI": "Finlande", "DK": "Danemark", "AT": "Autriche",
    "PL": "Pologne", "CZ": "République tchèque", "GR": "Grèce", "IE": "Irlande",
    "JP": "Japon", "KR": "Corée du Sud", "CN": "Chine", "IN": "Inde",
    "AU": "Australie", "NZ": "Nouvelle-Zélande", "BR": "Brésil", "MX": "Mexique",
    "AR": "Argentine", "CL": "Chili", "RU": "Russie", "UA": "Ukraine",
    "TR": "Turquie", "EG": "Égypte", "ZA": "Afrique du Sud", "NG": "Nigeria",
    "SA": "Arabie saoudite", "AE": "Émirats arabes unis", "QA": "Qatar",
    "IL": "Israël", "JO": "Jordanie", "LB": "Liban", "SN": "Sénégal",
    "CI": "Côte d'Ivoire", "CM": "Cameroun", "KE": "Kenya", "ET": "Éthiopie",
    "SG": "Singapour", "TH": "Thaïlande", "VN": "Viêt Nam", "ID": "Indonésie",
    "MY": "Malaisie", "PH": "Philippines",
    "XX": "Inconnu",
}


def _iso_to_flag(iso2: str) -> str:
    """Convert ISO 3166-1 alpha-2 code to flag emoji.

    Returns 🌐 for invalid codes and the standard "XX" unknown placeholder.
    """
    code = (iso2 or "").strip().upper()
    if len(code) != 2 or not code.isalpha() or code == "XX":
        return "🌐"
    base = 0x1F1E6  # regional indicator A
    return (
        chr(base + ord(code[0]) - ord("A"))
        + chr(base + ord(code[1]) - ord("A"))
    )


def _iso_to_name(iso2: str) -> str:
    code = (iso2 or "").strip().upper()
    return _ISO_TO_NAME_FR.get(code, code or "—")


def _safe_rows(query: str, params: tuple = ()) -> list:
    """Execute a SELECT and return rows, or [] on any error."""
    conn = _connect_ro()
    if conn is None:
        return []
    try:
        return list(conn.execute(query, params).fetchall())
    except sqlite3.OperationalError as exc:
        log.debug("[sentinel_metrics] rows soft-fail: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        log.debug("[sentinel_metrics] rows unexpected: %s", exc)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


# TRUTH ENGINE (2026-05-23) — exclude codes that aren't real ISO 3166-1
# alpha-2 destinations. XX and UNKNOWN are placeholders/sentinels and pollute
# the trust narrative on the landing.
_INVALID_COUNTRY_CODES = frozenset({"", "XX", "UNKNOWN", "UNK", "N/A", "NA"})


def _is_valid_iso_code(code: str | None) -> bool:
    if not code:
        return False
    c = code.strip().upper()
    if c in _INVALID_COUNTRY_CODES:
        return False
    if len(c) != 2 or not c.isalpha():
        return False
    return True


def get_countries_breakdown(limit: int = 10) -> list[dict]:
    """Top N countries by session count (descending).

    Reads sentinel_country_counters (zero-knowledge aggregate). Returns:
        [{"code": "DZ", "name": "Algérie", "flag": "🇩🇿", "count": 5}, ...]

    TRUTH ENGINE (2026-05-23) — filters out NULL / '' / XX / UNKNOWN
    so only real ISO codes reach the trust block.

    Fail-safe: returns [] if table missing or DB unavailable.
    """
    # Pull more rows than the limit so we can still get `limit` valid ones
    # after filtering out XX/UNKNOWN.
    rows = _safe_rows(
        "SELECT country_iso2, count FROM sentinel_country_counters "
        "WHERE country_iso2 IS NOT NULL AND country_iso2 != '' "
        "ORDER BY count DESC LIMIT ?",
        (max(1, int(limit)) * 3,),
    )
    out = []
    for r in rows:
        try:
            code = (r[0] or "").upper()
            cnt = int(r[1] or 0)
            if not _is_valid_iso_code(code) or cnt < 1:
                continue
            out.append({
                "code": code,
                "name": _iso_to_name(code),
                "flag": _iso_to_flag(code),
                "count": cnt,
            })
            if len(out) >= int(limit):
                break
        except Exception:
            continue
    return out


def get_country_count() -> int:
    """Distinct VALID ISO countries with at least one session.

    TRUTH ENGINE: only ISO 3166-1 alpha-2 codes are counted (XX/UNKNOWN excluded).
    """
    rows = _safe_rows(
        "SELECT country_iso2 FROM sentinel_country_counters "
        "WHERE country_iso2 IS NOT NULL AND country_iso2 != ''",
    )
    return sum(1 for r in rows if _is_valid_iso_code(r[0]))


def get_latest_countries(limit: int = 3) -> list[dict]:
    """Most recently seen countries.

    Source: sentinel_country_counters.last_seen_day (descending). Returns:
        [{"code": "DZ", "flag": "🇩🇿"}, ...]

    Privacy: country-level only, day-level only (no precise time, no IP,
    no session id). Fail-safe: returns [].
    """
    # TRUTH ENGINE: pull extra rows so we can filter XX/UNKNOWN then keep distinct.
    rows = _safe_rows(
        "SELECT country_iso2, last_seen_day FROM sentinel_country_counters "
        "WHERE country_iso2 IS NOT NULL AND country_iso2 != '' "
        "ORDER BY last_seen_day DESC, count DESC LIMIT ?",
        (max(1, int(limit)) * 4,),
    )
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        try:
            code = (r[0] or "").upper()
            if code in seen:
                continue
            if not _is_valid_iso_code(code):
                continue
            seen.add(code)
            out.append({"code": code, "flag": _iso_to_flag(code)})
            if len(out) >= int(limit):
                break
        except Exception:
            continue
    return out


# Public API — snapshot ---------------------------------------------------


def get_metrics_snapshot() -> dict[str, Any]:
    """One-shot dict for the public /api/sentinel/metrics endpoint.

    Single function = single DB round-trip path. UI never has to call
    multiple endpoints. Fail-safe: every field defaults to 0 / 0.0 / False / [].

    HONEST REDESIGN (2026-05-29):
      * total_sessions       = COUNT(*) FROM sentinel_sessions
      * completed_sessions   = state == 'ENDED' only
      * pending_sessions     = state IN PENDING_STATES (NEW key)
                               (PENDING_DRIVER | PENDING_PARENT)
      * interrupted_sessions = state IN INTERRUPTED_STATES
                               (EXPIRED | STOP_PENDING_PARENT | STOP_PENDING_DRIVER | FAILED)
      * active_sessions      = ACTIVE / STOP_PENDING_* AND not expired
      * success_rate         = round(completed/total*100) only IF
                               completed >= 1; otherwise None so the UI
                               can display "n/a — no session run to term"
                               instead of a misleading 0 % or 100 %.
      * countries            = top 10 by count, valid ISO codes only (XX excluded)
      * country_count        = distinct VALID ISO2 codes
      * latest_countries     = max 3 recent DISTINCT valid ISO codes

    JSON contract — both old and new key names are exposed (back-compat):
      active_users  ←→  active_sessions  (same value)
      feedback_avg  ←→  feedback_average (same value)
    """
    total = get_total_sessions()
    completed = get_completed_sessions()
    pending = get_pending_sessions()
    interrupted = get_interrupted_sessions()
    active = get_active_sessions()
    fb_count = get_feedback_count()
    fb_avg = get_feedback_average()

    # success_rate: only meaningful once at least one session has actually
    # been run to term. Reporting 0 % or 100 % when zero sessions ENDED
    # is misleading — either it overclaims (100 %) or it implies failure
    # where there has been no completed attempt at all (0 %).
    success_rate: int | None
    if completed > 0 and total > 0:
        success_rate = int(round(100.0 * completed / total))
    else:
        success_rate = None

    countries = get_countries_breakdown(limit=10)
    country_count = get_country_count()
    latest_countries = get_latest_countries(limit=3)

    return {
        "total_sessions": total,
        "completed_sessions": completed,
        "pending_sessions": pending,
        "interrupted_sessions": interrupted,
        "success_rate": success_rate,
        # Both naming conventions exposed — back-compat with existing JS that
        # reads active_users / feedback_avg, plus the new brief contract names.
        "active_users": active,
        "active_sessions": active,
        "feedback_count": fb_count,
        "feedback_avg": fb_avg,
        "feedback_average": fb_avg,
        "countries": countries,
        "country_count": country_count,
        "latest_countries": latest_countries,
        "ok": True,
        # Cache hint for the front-end: 30 s.
        "cache_ttl_s": 30,
    }


# Public API — counters (NO-OP, kept for brief compliance) ---------------


def increment_total_sessions() -> None:
    """NO-OP. Metrics derive from sentinel_sessions SQL COUNT.

    Kept for brief compliance and to be a clear hook target if a future
    refactor wants a write-side cache (sentinel_metrics table is available
    for that purpose). Today: pure debug log.
    """
    log.debug("[sentinel_metrics] increment_total_sessions called (no-op, SQL-first)")


def increment_completed_sessions() -> None:
    """NO-OP. Counterpart to increment_total_sessions. See its docstring."""
    log.debug("[sentinel_metrics] increment_completed_sessions called (no-op, SQL-first)")


__all__ = [
    "get_active_sessions",
    "get_completed_sessions",
    "get_pending_sessions",
    "get_interrupted_sessions",
    "get_protected_sessions",
    "get_countries_breakdown",
    "get_country_count",
    "get_latest_countries",
    "get_feedback_average",
    "get_feedback_count",
    "get_metrics_snapshot",
    "get_total_sessions",
    "increment_completed_sessions",
    "increment_total_sessions",
]
