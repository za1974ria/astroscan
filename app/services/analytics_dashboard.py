"""Analytics dashboard helpers — readonly snapshot pour /analytics page.

PASS COCKPIT (2026-05-22) — Refonte complète des agrégations pour
exclure systématiquement les IPs propriétaire (env ASTROSCAN_OWNER_IPS
+ table owner_ips + range 105.235.13.0/24). Ajout de `load_cockpit_payload`
qui sert toutes les données du nouveau dashboard cyan ORBITAL-CHOHRA :
KPIs cohérents avec visits.count, timeline 7j/30j/90j, peak_hour,
top_countries/pages, recent_visitors anonymisés.

Fonctions exposées :
    analytics_empty_payload() -> dict
    load_analytics_readonly() -> dict        # legacy (conservé)
    load_cockpit_payload(window_days=30)     # nouveau dashboard
    owner_ip_sql_filter() -> tuple(str, list)  # snippet WHERE + params
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import DB_PATH

log = logging.getLogger(__name__)

OWNER_IP_LIKE_PREFIXES = ("105.235.13.%",)


def _analytics_tz_for_country_code(code):
    c = (code or "").strip().upper()
    if c == "US":
        return "America/Los_Angeles"
    if c == "DZ":
        return "Africa/Algiers"
    if c == "BR":
        return "America/Sao_Paulo"
    return "UTC"


def _analytics_fmt_duration_sec(sec):
    try:
        s = int(sec)
    except Exception:
        return "—"
    s = max(0, s)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}"
    if m > 0:
        return f"{m}m{s:02d}"
    return f"{s}s"


def _analytics_journey_display(journey_raw):
    if not journey_raw:
        return "—"
    parts = [p.strip() for p in str(journey_raw).split(",") if p.strip()]
    if not parts:
        return "—"
    return " → ".join(parts)


def _analytics_start_local_display(start_iso, country_code):
    try:
        from zoneinfo import ZoneInfo
        raw = (start_iso or "").strip()
        if not raw:
            return "—"
        tzname = _analytics_tz_for_country_code(country_code)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tzname))
        return local.strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return (start_iso or "—") if start_iso else "—"


def _analytics_time_hms_local(iso_str, country_code):
    try:
        from zoneinfo import ZoneInfo
        raw = (iso_str or "").strip()
        if not raw:
            return "—"
        tzname = _analytics_tz_for_country_code(country_code)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tzname))
        return local.strftime("%H:%M:%S")
    except Exception:
        return "—"


def _analytics_session_classification(total_sec, page_count):
    try:
        t = int(total_sec)
    except Exception:
        t = 0
    try:
        n = int(page_count)
    except Exception:
        n = 0
    if t > 180 and n > 5:
        return "Inspection approfondie"
    if n > 3:
        return "Exploration active"
    return "Passage rapide"


def analytics_empty_payload():
    return {
        "total_visits": 0,
        "unique_ips": 0,
        "total_tracked_events": 0,
        "last_activity": "—",
        "top_countries": [],
        "top_cities": [],
        "latest_visits": [],
        "top_pages_by_time": [],
        "avg_duration_by_page": [],
        "longest_sessions": [],
        "session_visitors_detail": [],
        "sessions_timeline": [],
        "bot_count": 0,
    }


def _country_flag_emoji(code: str) -> str:
    c = (code or "").strip().upper()
    if len(c) != 2 or not c.isalpha():
        return "🏳"
    base = 0x1F1E6
    return chr(base + ord(c[0]) - ord("A")) + chr(base + ord(c[1]) - ord("A"))


def owner_ip_sql_filter(owner_ips: set | None = None) -> tuple[str, list]:
    """Retourne un fragment SQL (clause AND ...) + params pour exclure
    les IPs propriétaire. Filtre cumulatif :
      - is_bot=0 AND is_owner=0 (flags stockés à l'insert)
      - ip NOT LIKE chaque préfixe (range 105.235.13.0/24)
      - ip NOT IN (owner_ips chargées à chaud)
    Le second filtre attrape les IPs récemment ajoutées qui n'avaient pas
    is_owner=1 au moment de l'insertion historique."""
    fragments = ["is_bot = 0", "is_owner = 0"]
    params: list = []
    for pref in OWNER_IP_LIKE_PREFIXES:
        fragments.append("ip NOT LIKE ?")
        params.append(pref)
    if owner_ips:
        placeholders = ",".join(["?"] * len(owner_ips))
        fragments.append(f"ip NOT IN ({placeholders})")
        params.extend(sorted(owner_ips))
    return " AND ".join(fragments), params


# ─────────────────────────────────────────────────────────────────────
# CANONICAL VISITOR TRUTH (2026-05-29)
# Every visitor counter rendered anywhere in the app — banner, cockpit,
# /api/visitors/stats, /api/visitors/snapshot, a_propos block, research
# dashboard — must derive from this function. No endpoint is allowed to
# redefine "unique visitors" with its own COUNT query. The canonical
# filter is owner_ip_sql_filter() (is_bot=0 AND is_owner=0 + IP ranges
# + env-loaded owner IPs).
# ─────────────────────────────────────────────────────────────────────
def get_visitor_truth(owner_ips: set | None = None) -> dict:
    """Single source of truth for visitor metrics. Fail-safe defaults to 0.

    Returns a dict with exactly the keys below. One DB connection,
    read-only queries, global try/except — never raises. Callers are
    expected to map these canonical values onto their existing JSON
    shapes rather than reissue COUNT queries.

    Keys:
      unique_visitors      — COUNT(DISTINCT ip), filtered
      human_sessions       — COUNT(DISTINCT session_id), filtered
      total_visits         — COUNT(*), filtered (= raw human visits)
      visits_counter       — visits.count (historical passage counter)
      today_unique         — COUNT(DISTINCT ip) today, filtered
      distinct_countries   — COUNT(DISTINCT country_code) with valid ISO
      by_country           — top 50, COUNT(DISTINCT ip), NL normalised
      generated_at         — UTC isoformat (Z)
    """
    from datetime import datetime, timezone

    payload = {
        "unique_visitors": 0,
        "human_sessions": 0,
        "total_visits": 0,
        "visits_counter": 0,
        "today_unique": 0,
        "distinct_countries": 0,
        "by_country": [],
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    where_owner, params_owner = owner_ip_sql_filter(owner_ips)

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        row = cur.execute(
            f"SELECT COUNT(DISTINCT ip) AS c FROM visitor_log WHERE {where_owner}",
            params_owner,
        ).fetchone()
        payload["unique_visitors"] = int(row["c"] or 0) if row else 0

        row = cur.execute(
            f"SELECT COUNT(DISTINCT session_id) AS c FROM visitor_log WHERE {where_owner}",
            params_owner,
        ).fetchone()
        payload["human_sessions"] = int(row["c"] or 0) if row else 0

        row = cur.execute(
            f"SELECT COUNT(*) AS c FROM visitor_log WHERE {where_owner}",
            params_owner,
        ).fetchone()
        payload["total_visits"] = int(row["c"] or 0) if row else 0

        try:
            row = cur.execute("SELECT count FROM visits WHERE id=1").fetchone()
            payload["visits_counter"] = int(row["count"] or 0) if row else 0
        except Exception:
            payload["visits_counter"] = 0

        row = cur.execute(
            f"SELECT COUNT(DISTINCT ip) AS c FROM visitor_log "
            f"WHERE {where_owner} AND date(visited_at)=date('now')",
            params_owner,
        ).fetchone()
        payload["today_unique"] = int(row["c"] or 0) if row else 0

        row = cur.execute(
            f"SELECT COUNT(DISTINCT country_code) AS c FROM visitor_log "
            f"WHERE {where_owner} "
            f"AND country_code IS NOT NULL AND country_code != '' "
            f"AND country_code != 'XX' AND country != 'Unknown'",
            params_owner,
        ).fetchone()
        payload["distinct_countries"] = int(row["c"] or 0) if row else 0

        rows = cur.execute(
            "SELECT CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country, "
            "country_code, COUNT(DISTINCT ip) AS cnt "
            "FROM visitor_log "
            f"WHERE {where_owner} AND country != 'Unknown' "
            "GROUP BY CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END, country_code "
            "ORDER BY cnt DESC LIMIT 50",
            params_owner,
        ).fetchall()
        payload["by_country"] = [
            {
                "country": r["country"],
                "code": (r["country_code"] or "XX"),
                "count": int(r["cnt"] or 0),
            }
            for r in rows
            if (r["country_code"] or "XX").upper() != "XX"
            and "inconnu" not in (r["country"] or "").lower()
        ]

        conn.close()
    except Exception:
        return payload
    return payload


def load_analytics_readonly():
    """Lecture seule SQLite (visitor_log, session_time). Conservée pour compat
    avec d'éventuels callers legacy ; le dashboard cockpit utilise désormais
    `load_cockpit_payload`."""
    out = analytics_empty_payload()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        last_candidates = []

        if "visitor_log" in tables:
            r = cur.execute("SELECT COUNT(*) AS c FROM visitor_log").fetchone()
            out["total_visits"] = int(r["c"] if r else 0)
            # Apply the canonical owner/bot filter so unique_ips here matches
            # what the cockpit and the GEO-IP tracker report — no more drift
            # between three different "unique visitors" numbers.
            _where_owner, _params_owner = owner_ip_sql_filter()
            r = cur.execute(
                f"SELECT COUNT(DISTINCT ip) AS c FROM visitor_log WHERE {_where_owner}",
                _params_owner,
            ).fetchone()
            out["unique_ips"] = int(r["c"] if r else 0)
            m = cur.execute("SELECT MAX(visited_at) AS m FROM visitor_log").fetchone()
            if m and m["m"]:
                last_candidates.append(str(m["m"]))

        if "session_time" in tables:
            r = cur.execute("SELECT COUNT(*) AS c FROM session_time").fetchone()
            out["total_tracked_events"] = int(r["c"] if r else 0)
            m = cur.execute("SELECT MAX(created_at) AS m FROM session_time").fetchone()
            if m and m["m"]:
                last_candidates.append(str(m["m"]))

        if last_candidates:
            out["last_activity"] = max(last_candidates)

        conn.close()
    except Exception:
        return analytics_empty_payload()
    return out


def load_cockpit_payload(window_days: int = 30, owner_ips: set | None = None) -> dict:
    """Charge tout le payload du dashboard cockpit cyan.

    Args:
        window_days: fenêtre temporelle pour top_countries / top_pages /
            recent_visitors (par défaut 30 jours). Les timelines 7j et 30j
            sont toujours calculées en parallèle.
        owner_ips: ensemble d'IPs propriétaire à exclure (chargé via
            db_visitors._load_owner_ips()). Peut être None.

    Returns:
        dict avec les clés attendues par templates/analytics.html.
    """
    payload = {
        "total_unique_visitors": 0,
        "human_sessions": 0,
        "visits_counter": 0,
        "unique_ips_count": 0,
        "countries_count": 0,
        "avg_session_duration_sec": 0,
        "avg_session_duration_fmt": "—",
        "pages_per_session": 0.0,
        "peak_hour_utc": "—",
        "peak_hour_count": 0,
        "bot_count": 0,
        "last_activity": "—",
        "is_live": False,
        "top_countries": [],
        "top_pages": [],
        "timeline_7d": {"labels": [], "data": []},
        "timeline_30d": {"labels": [], "data": []},
        "hour_distribution": [0] * 24,
        "recent_visitors": [],
    }

    owner_ips = owner_ips or set()
    where_owner, params_owner = owner_ip_sql_filter(owner_ips)

    # All visitor KPIs derive from the canonical truth function so the
    # cockpit can never drift from the GEO-IP tracker or /api/visitors/stats.
    truth = get_visitor_truth(owner_ips)
    payload["visits_counter"] = truth["visits_counter"]
    payload["human_sessions"] = truth["human_sessions"]
    payload["unique_ips_count"] = truth["unique_visitors"]
    payload["total_unique_visitors"] = truth["unique_visitors"]
    payload["countries_count"] = truth["distinct_countries"]

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        row = cur.execute(
            "SELECT COUNT(*) AS c FROM visitor_log WHERE is_bot=1"
        ).fetchone()
        payload["bot_count"] = int(row["c"] or 0) if row else 0

        # ── Durée moyenne de session
        row = cur.execute(
            "SELECT AVG(total) AS a FROM ("
            "  SELECT SUM(duration) AS total FROM session_time "
            "  WHERE duration > 0 AND duration < 3600 "
            "  GROUP BY session_id"
            ")"
        ).fetchone()
        avg_dur = int(row["a"] or 0) if row else 0
        payload["avg_session_duration_sec"] = avg_dur
        payload["avg_session_duration_fmt"] = _analytics_fmt_duration_sec(avg_dur)

        # ── Pages par session (page_views joinTable visitor_log filtré)
        row = cur.execute(
            f"SELECT COUNT(*) AS pv FROM page_views pv "
            f"WHERE EXISTS (SELECT 1 FROM visitor_log vl "
            f"  WHERE vl.session_id = pv.session_id AND {where_owner})",
            params_owner,
        ).fetchone()
        total_pv = int(row["pv"] or 0) if row else 0
        if payload["human_sessions"] > 0:
            payload["pages_per_session"] = round(total_pv / payload["human_sessions"], 2)

        # ── Top countries (window_days)
        rows = cur.execute(
            f"SELECT "
            f"  CASE WHEN country_code='NL' THEN 'Netherlands' ELSE country END AS country, "
            f"  country_code, COUNT(*) AS c "
            f"FROM visitor_log "
            f"WHERE {where_owner} AND country != 'Unknown' AND country_code != 'XX' "
            f"  AND visited_at >= datetime('now', '-{int(window_days)} days') "
            f"GROUP BY country, country_code "
            f"ORDER BY c DESC LIMIT 10",
            params_owner,
        ).fetchall()
        top_countries = []
        max_c = max((r["c"] for r in rows), default=1) or 1
        for r in rows:
            top_countries.append({
                "country": r["country"],
                "code": r["country_code"] or "XX",
                "flag": _country_flag_emoji(r["country_code"] or ""),
                "count": int(r["c"]),
                "pct": round(100.0 * int(r["c"]) / max_c, 1),
            })
        payload["top_countries"] = top_countries

        # ── Top pages (page_views joinTable visitor_log filtré, hors /static)
        rows = cur.execute(
            f"SELECT pv.path AS path, COUNT(*) AS c FROM page_views pv "
            f"WHERE pv.path NOT LIKE '/static%' AND pv.path NOT LIKE '/api/%' "
            f"  AND pv.visited_at >= datetime('now', '-{int(window_days)} days') "
            f"  AND EXISTS (SELECT 1 FROM visitor_log vl "
            f"    WHERE vl.session_id = pv.session_id AND {where_owner}) "
            f"GROUP BY pv.path ORDER BY c DESC LIMIT 10",
            params_owner,
        ).fetchall()
        payload["top_pages"] = [
            {"path": r["path"] or "/", "count": int(r["c"])} for r in rows
        ]

        # ── Timeline 7d et 30d (DATE(visited_at) GROUP BY)
        for window in (7, 30):
            rows = cur.execute(
                f"SELECT DATE(visited_at) AS d, COUNT(DISTINCT session_id) AS c "
                f"FROM visitor_log "
                f"WHERE {where_owner} "
                f"  AND visited_at >= datetime('now', '-{window} days') "
                f"GROUP BY DATE(visited_at) ORDER BY d ASC",
                params_owner,
            ).fetchall()
            day_map = {r["d"]: int(r["c"]) for r in rows}
            labels = []
            data = []
            today = datetime.now(timezone.utc).date()
            for i in range(window - 1, -1, -1):
                d = today - timedelta(days=i)
                key = d.isoformat()
                labels.append(d.strftime("%d/%m"))
                data.append(day_map.get(key, 0))
            payload[f"timeline_{window}d"] = {"labels": labels, "data": data}

        # ── Distribution horaire (peak_hour)
        rows = cur.execute(
            f"SELECT CAST(strftime('%H', visited_at) AS INTEGER) AS h, COUNT(*) AS c "
            f"FROM visitor_log WHERE {where_owner} "
            f"GROUP BY h ORDER BY h ASC",
            params_owner,
        ).fetchall()
        hours = [0] * 24
        peak_h = 0
        peak_c = 0
        for r in rows:
            h = int(r["h"] or 0)
            if 0 <= h < 24:
                hours[h] = int(r["c"])
                if hours[h] > peak_c:
                    peak_c = hours[h]
                    peak_h = h
        payload["hour_distribution"] = hours
        payload["peak_hour_utc"] = f"{peak_h:02d}h" if peak_c > 0 else "—"
        payload["peak_hour_count"] = peak_c

        # ── Recent visitors (10 derniers, anonymisés)
        rows = cur.execute(
            f"SELECT country, country_code, path, visited_at FROM visitor_log "
            f"WHERE {where_owner} "
            f"ORDER BY id DESC LIMIT 10",
            params_owner,
        ).fetchall()
        recent = []
        last_iso = None
        for r in rows:
            cc = (r["country_code"] or "XX").upper()
            visited = (r["visited_at"] or "").strip()
            if not last_iso and visited:
                last_iso = visited
            try:
                dt = datetime.fromisoformat(visited.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                hhmm = dt.astimezone(timezone.utc).strftime("%H:%M")
            except Exception:
                hhmm = "—"
            path = (r["path"] or "/")
            if len(path) > 32:
                path = path[:29] + "…"
            recent.append({
                "flag": _country_flag_emoji(cc),
                "code": cc,
                "country": r["country"] or "—",
                "time_utc": hhmm,
                "path": path,
            })
        payload["recent_visitors"] = recent
        if last_iso:
            payload["last_activity"] = last_iso
            try:
                dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta = datetime.now(timezone.utc) - dt
                payload["is_live"] = delta.total_seconds() < 300
            except Exception:
                pass

        conn.close()
    except Exception as exc:
        log.warning("load_cockpit_payload: %s", exc)
    return payload


_analytics_empty_payload = analytics_empty_payload
_load_analytics_readonly = load_analytics_readonly
