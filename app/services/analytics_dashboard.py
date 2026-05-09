"""Analytics dashboard helpers — readonly snapshot pour /analytics page.

Extrait de station_web.py (PASS 16) pour permettre l'utilisation
par analytics_bp sans dépendance circulaire.

PASS 27.7 (2026-05-09) — Ajout des 6 helpers `_analytics_*` (déplacés
verbatim depuis station_web.py L825-912). Avant ce PASS, ces helpers
étaient utilisés mais non importés ici, ce qui aurait provoqué un
NameError au runtime sur la route /analytics. Le déplacement résout ce
bug latent et fait de ce module la source de vérité unique.

Fonctions exposées :
    analytics_empty_payload() -> dict
    load_analytics_readonly() -> dict        # Lecture seule visitor_log + session_time
    _analytics_tz_for_country_code(code)
    _analytics_fmt_duration_sec(sec)
    _analytics_journey_display(journey_raw)
    _analytics_start_local_display(start_iso, country_code)
    _analytics_time_hms_local(iso_str, country_code)
    _analytics_session_classification(total_sec, page_count)
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from app.config import DB_PATH

log = logging.getLogger(__name__)


def _analytics_tz_for_country_code(code):
    """Fuseau indicatif pour heure locale (US / DZ / BR)."""
    c = (code or "").strip().upper()
    if c == "US":
        return "America/Los_Angeles"
    if c == "DZ":
        return "Africa/Algiers"
    if c == "BR":
        return "America/Sao_Paulo"
    return "UTC"


def _analytics_fmt_duration_sec(sec):
    """Ex. 125 → 2m05."""
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
    """Heure locale au début de session selon country_code."""
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
    """Heure locale HH:MM:SS pour une ligne de timeline."""
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
    """Profil comportemental (nombre de vues = lignes session_time)."""
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


def load_analytics_readonly():
    """Lecture seule SQLite (visitor_log, session_time). Jamais de levée vers l'utilisateur."""
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
            r = cur.execute(
                "SELECT COUNT(DISTINCT ip) AS c FROM visitor_log "
                "WHERE ip NOT IN ('127.0.0.1', '::1')"
            ).fetchone()
            out["unique_ips"] = int(r["c"] if r else 0)
            # PASS 27 — Normalize NL duplicate at query time.
            out["top_countries"] = [
                {"country": row[0], "code": row[1] or "", "count": row[2]}
                for row in cur.execute(
                    "SELECT CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country, "
                    "country_code, COUNT(*) AS cnt FROM visitor_log "
                    "WHERE country != 'Unknown' "
                    "GROUP BY CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END, country_code "
                    "ORDER BY cnt DESC LIMIT 15"
                ).fetchall()
            ]
            out["top_cities"] = [
                {"country": row[0], "city": row[1], "count": row[2]}
                for row in cur.execute(
                    "SELECT CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country, "
                    "city, COUNT(*) AS cnt FROM visitor_log "
                    "WHERE ip NOT IN ('127.0.0.1', '::1') "
                    "GROUP BY CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END, city "
                    "ORDER BY cnt DESC LIMIT 15"
                ).fetchall()
            ]
            out["latest_visits"] = [
                {
                    "ip": row["ip"],
                    "country": row["country"],
                    "city": row["city"],
                    "path": row["path"],
                    "visited_at": row["visited_at"],
                }
                for row in cur.execute(
                    "SELECT ip, country, city, path, visited_at "
                    "FROM visitor_log ORDER BY id DESC LIMIT 10"
                )
            ]
            m = cur.execute("SELECT MAX(visited_at) AS m FROM visitor_log").fetchone()
            if m and m["m"]:
                last_candidates.append(str(m["m"]))

        if "session_time" in tables:
            r = cur.execute("SELECT COUNT(*) AS c FROM session_time").fetchone()
            out["total_tracked_events"] = int(r["c"] if r else 0)
            out["top_pages_by_time"] = [
                {"path": row[0] or "", "total_seconds": int(row[1] or 0)}
                for row in cur.execute(
                    "SELECT path, COALESCE(SUM(duration), 0) AS s FROM session_time "
                    "GROUP BY path ORDER BY s DESC LIMIT 15"
                ).fetchall()
            ]
            out["avg_duration_by_page"] = [
                {"path": row[0] or "", "avg_seconds": round(float(row[1] or 0), 2)}
                for row in cur.execute(
                    "SELECT path, AVG(duration) AS a FROM session_time "
                    "GROUP BY path ORDER BY a DESC LIMIT 15"
                ).fetchall()
            ]
            out["longest_sessions"] = [
                {
                    "session_id": row["session_id"] or "",
                    "path": row["path"] or "",
                    "duration": int(row["duration"] or 0),
                    "created_at": row["created_at"] or "",
                }
                for row in cur.execute(
                    "SELECT session_id, path, duration, created_at FROM session_time "
                    "ORDER BY duration DESC LIMIT 10"
                )
            ]
            out["session_visitors_detail"] = []
            try:
                if "visitor_log" in tables:
                    detail_rows = cur.execute(
                        """
                        SELECT
                          st.session_id AS sid,
                          COALESCE(SUM(st.duration), 0) AS total_time,
                          COUNT(*) AS pages_count,
                          GROUP_CONCAT(st.path ORDER BY st.created_at) AS journey,
                          MIN(st.created_at) AS start_time,
                          MAX(st.created_at) AS end_time,
                          (SELECT country FROM visitor_log v
                           WHERE v.session_id = st.session_id
                           ORDER BY v.id DESC LIMIT 1) AS country,
                          (SELECT city FROM visitor_log v
                           WHERE v.session_id = st.session_id
                           ORDER BY v.id DESC LIMIT 1) AS city,
                          (SELECT country_code FROM visitor_log v
                           WHERE v.session_id = st.session_id
                           ORDER BY v.id DESC LIMIT 1) AS country_code
                        FROM session_time st
                        WHERE st.session_id IS NOT NULL AND TRIM(st.session_id) != ''
                        GROUP BY st.session_id
                        ORDER BY COALESCE(SUM(st.duration), 0) DESC
                        LIMIT 20
                        """
                    ).fetchall()
                else:
                    detail_rows = cur.execute(
                        """
                        SELECT
                          st.session_id AS sid,
                          COALESCE(SUM(st.duration), 0) AS total_time,
                          COUNT(*) AS pages_count,
                          GROUP_CONCAT(st.path ORDER BY st.created_at) AS journey,
                          MIN(st.created_at) AS start_time,
                          MAX(st.created_at) AS end_time,
                          NULL AS country,
                          NULL AS city,
                          NULL AS country_code
                        FROM session_time st
                        WHERE st.session_id IS NOT NULL AND TRIM(st.session_id) != ''
                        GROUP BY st.session_id
                        ORDER BY COALESCE(SUM(st.duration), 0) DESC
                        LIMIT 20
                        """
                    ).fetchall()
                for dr in detail_rows:
                    cc = dr["country_code"] if dr["country_code"] is not None else ""
                    st_iso = dr["start_time"]
                    out["session_visitors_detail"].append(
                        {
                            "session_id": dr["sid"] or "",
                            "country": dr["country"] or "—",
                            "city": dr["city"] or "—",
                            "total_time_fmt": _analytics_fmt_duration_sec(dr["total_time"]),
                            "pages_count": int(dr["pages_count"] or 0),
                            "journey": _analytics_journey_display(dr["journey"]),
                            "start_time": st_iso or "—",
                            "end_time": dr["end_time"] or "—",
                            "start_local": _analytics_start_local_display(st_iso, cc),
                        }
                    )
            except Exception:
                out["session_visitors_detail"] = []
            out["sessions_timeline"] = []
            try:
                t_rows = cur.execute(
                    "SELECT session_id, path, duration, created_at FROM session_time "
                    "WHERE session_id IS NOT NULL AND TRIM(session_id) != '' "
                    "ORDER BY session_id ASC, created_at ASC"
                ).fetchall()
                sessions_detail = {}
                for tr in t_rows:
                    sid = tr["session_id"]
                    if sid not in sessions_detail:
                        sessions_detail[sid] = {"events": []}
                    sessions_detail[sid]["events"].append(
                        {
                            "path": tr["path"] or "",
                            "duration": tr["duration"],
                            "time": tr["created_at"],
                        }
                    )
                if sessions_detail:
                    sids_ordered = sorted(
                        sessions_detail.keys(),
                        key=lambda s: max(
                            str(e["time"]) for e in sessions_detail[s]["events"]
                        ),
                        reverse=True,
                    )[:10]
                    for sid in sids_ordered:
                        country = city = ip = ua = ""
                        cc = ""
                        if "visitor_log" in tables:
                            gr = cur.execute(
                                "SELECT country, city, country_code, ip, user_agent "
                                "FROM visitor_log "
                                "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                                (sid,),
                            ).fetchone()
                            if gr:
                                country = gr["country"] or ""
                                city = gr["city"] or ""
                                cc = gr["country_code"] or ""
                                ip = gr["ip"] or ""
                                _ua = gr["user_agent"] or ""
                                ua = (
                                    _ua
                                    if len(_ua) <= 220
                                    else _ua[:217] + "..."
                                )
                        evlist = sessions_detail[sid]["events"]
                        first_t = min(str(e["time"]) for e in evlist)
                        total_time = 0
                        for e in evlist:
                            try:
                                total_time += int(e["duration"] or 0)
                            except Exception:
                                pass
                        n_events = len(evlist)
                        seen_paths = set()
                        modules = []
                        for e in evlist:
                            p = (e["path"] or "").strip()
                            if p and p not in seen_paths:
                                seen_paths.add(p)
                                modules.append(p)
                        sess = {
                            "session_id": sid,
                            "country": country or "—",
                            "city": city or "—",
                            "ip": ip or "—",
                            "ua": ua or "—",
                            "total_time": total_time,
                            "total_time_fmt": _analytics_fmt_duration_sec(
                                total_time
                            ),
                            "classification": _analytics_session_classification(
                                total_time, n_events
                            ),
                            "modules": modules,
                            "start_local": _analytics_start_local_display(
                                first_t, cc
                            ),
                            "events": [
                                {
                                    "time_local": _analytics_time_hms_local(
                                        e["time"], cc
                                    ),
                                    "path": e["path"],
                                    "duration_fmt": _analytics_fmt_duration_sec(
                                        e["duration"]
                                    ),
                                }
                                for e in evlist
                            ],
                        }
                        ip = sess.get("ip")
                        geo = get_geo_from_ip(ip)
                        sess["country"] = geo.get("country")
                        sess["city"] = geo.get("city")
                        if not sess.get("country"):
                            sess["country"] = country or "—"
                        if not sess.get("city"):
                            sess["city"] = city or "—"
                        visit_count = len(sess["events"])
                        modules_str = ", ".join(sess["modules"][:4])
                        if len(sess["modules"]) > 4:
                            modules_str += "..."
                        sess["summary_line"] = (
                            f"🌍 {sess.get('country', '—')} - {sess.get('city', '—')} | "
                            f"🕒 {sess.get('start_local', '—')} | "
                            f"👁 {visit_count} visites | "
                            f"⏱ {sess.get('total_time_fmt', '—')} | "
                            f"📊 {modules_str if modules_str else '—'}"
                        )
                        out["sessions_timeline"].append(sess)
            except Exception:
                out["sessions_timeline"] = []
            m = cur.execute("SELECT MAX(created_at) AS m FROM session_time").fetchone()
            if m and m["m"]:
                last_candidates.append(str(m["m"]))

        if last_candidates:
            out["last_activity"] = max(last_candidates)

        conn.close()
    except Exception:
        return analytics_empty_payload()
    return out

# Compat aliases
_analytics_empty_payload = analytics_empty_payload
_load_analytics_readonly = load_analytics_readonly
