"""Blueprint Analytics — endpoints de tracking visiteurs + dashboard.

Endpoints :
  - /api/visits             (GET)  : compteur actuel
  - /api/visits/increment   (POST) : incremente et retourne nouvelle valeur
  - /api/visits/reset       (POST) : reset compteur (admin)
  - /api/visits/count       (GET)  : compteur direct via SQLite
  - /analytics              (GET)  : dashboard HTML (PASS 16)
  - /api/visitors/connection_time (PASS 16)
  + 10 routes PASS 12 (owner-ips, score-update, summary, globe, stream, ...)

Migration depuis station_web.py (CTO Critique 3 - Monolith reduction).
"""

import logging
import os
import sqlite3

from flask import Blueprint, jsonify, redirect, render_template, request

log = logging.getLogger(__name__)

bp = Blueprint("analytics_bp", __name__)

DB_PATH = "/root/astro_scan/data/archive_stellaire.db"


@bp.route("/api/visits", methods=["GET"])
def api_visits_get():
    """Retourne le nombre actuel de visites."""
    from station_web import _get_visits_count
    try:
        count = _get_visits_count()
        return jsonify({"count": count})
    except Exception as e:
        log.warning(f"api/visits: {e}")
        return jsonify({"count": 0})


@bp.route("/api/visits/increment", methods=["POST"])
def api_visits_increment():
    """Incremente le compteur et retourne la nouvelle valeur."""
    from station_web import _increment_visits, _get_visits_count
    try:
        count = _increment_visits()
        return jsonify({"count": count})
    except Exception as e:
        log.warning(f"api/visits/increment: {e}")
        return jsonify({"count": _get_visits_count()})


@bp.route("/api/visits/reset", methods=["POST"])
def reset_visits():
    """Reset compteur de visites - admin seulement."""
    try:
        conn = sqlite3.connect(DB_PATH)
        old = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()
        conn.execute("UPDATE visits SET count = 0 WHERE id=1")
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "old_count": old[0] if old else 0, "new_count": 0})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/visits/count")
def get_visits():
    """Retourne le compteur de visites actuel (lecture directe SQLite)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()
        conn.close()
        return jsonify({"count": row[0] if row else 0})
    except Exception as e:
        return jsonify({"count": 0, "error": str(e)})



@bp.route("/api/visitors/snapshot")
def api_visitors_snapshot():
    """REST one-shot : meme payload que le SSE - polling fallback."""
    from station_web import get_global_stats
    try:
        exclude_my_ip = (request.args.get("exclude_my_ip", "1") or "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        return jsonify(get_global_stats(exclude_my_ip=exclude_my_ip))
    except Exception as e:
        log.warning("visitors/snapshot: %s", e)
        return jsonify({
            "error": str(e), "total": 0, "online_now": 0, "top_countries": [],
            "last_connections": [], "heatmap": [], "humans_total": 0,
            "bots_total": 0, "humans_today": 0,
        })


@bp.route("/api/visitors/connection-time")
def api_visitors_connection_time_legacy():
    """Redirige 301 vers la version underscore (URL canonique)."""
    return redirect("/api/visitors/connection_time", code=301)


# ── PASS 12 — Owner IPs CRUD (Domaine AI) ─────────────────────────────
@bp.route("/api/owner-ips", methods=["POST"])
def api_owner_ips_add():
    """Ajoute une IP propriétaire. Body JSON: {"ip": "x.x.x.x", "label": "Maison"}"""
    from station_web import _get_db_visitors, _invalidate_owner_ips_cache
    try:
        data = request.get_json(force=True, silent=True) or {}
        ip = (data.get("ip") or "").strip()
        label = (data.get("label") or "")[:100].strip()
        if not ip:
            return jsonify({"ok": False, "error": "ip manquant"}), 400
        conn = _get_db_visitors()
        conn.execute(
            "INSERT OR REPLACE INTO owner_ips (ip, label, added_at) VALUES (?, ?, datetime('now'))",
            (ip, label),
        )
        conn.execute("UPDATE visitor_log SET is_owner=1 WHERE ip=?", (ip,))
        conn.commit()
        conn.close()
        _invalidate_owner_ips_cache()
        return jsonify({"ok": True, "ip": ip})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/owner-ips/<int:ip_id>", methods=["DELETE"])
def api_owner_ips_delete(ip_id):
    """Supprime une IP propriétaire par son ID."""
    from station_web import _get_db_visitors, _invalidate_owner_ips_cache
    try:
        conn = _get_db_visitors()
        row = conn.execute("SELECT ip FROM owner_ips WHERE id=?", (ip_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({"ok": False, "error": "IP non trouvée"}), 404
        ip = row[0]
        conn.execute("DELETE FROM owner_ips WHERE id=?", (ip_id,))
        conn.execute("UPDATE visitor_log SET is_owner=0 WHERE ip=?", (ip,))
        conn.commit()
        conn.close()
        _invalidate_owner_ips_cache()
        return jsonify({"ok": True, "removed_ip": ip})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── PASS 12 — Visitor scoring (JS beacon) ─────────────────────────────
@bp.route("/api/visitor/score-update", methods=["POST"])
def api_visitor_score_update():
    """Beacon JS : met à jour le human_score (JS activé, temps sur page)."""
    from station_web import _get_db_visitors, _compute_human_score
    try:
        data = request.get_json(force=True, silent=True) or {}
        sid = (data.get("session_id") or "")[:128].strip()
        duration = int(data.get("duration_sec") or 0)
        js_active = bool(data.get("js", False))
        if not sid:
            return jsonify({"ok": False}), 400
        conn = _get_db_visitors()
        row = conn.execute(
            "SELECT ip, user_agent FROM visitor_log WHERE session_id=? LIMIT 1", (sid,)
        ).fetchone()
        if row:
            ip, ua = row[0], row[1]
            page_cnt = conn.execute(
                "SELECT COUNT(*) FROM page_views WHERE session_id=?", (sid,)
            ).fetchone()[0]
            referrer = (request.headers.get("Referer") or "")
            score = _compute_human_score(
                ua or "", page_count=page_cnt, session_sec=duration,
                referrer=referrer, js_beacon=js_active,
            )
            conn.execute(
                "UPDATE visitor_log SET human_score=? WHERE session_id=? AND ip=?",
                (score, sid, ip),
            )
            conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        log.debug("score-update: %s", e)
        return jsonify({"ok": False}), 200


# ── PASS 12 — Analytics summary (KPIs + top pages/pays/owner) ─────────
@bp.route("/api/analytics/summary", methods=["GET"])
def api_analytics_summary():
    """JSON summary pour dashboard : visiteurs, pages vues, human%, top pages, owner."""
    from station_web import _get_db_visitors
    try:
        conn = _get_db_visitors()
        conn.row_factory = sqlite3.Row

        total_sessions = conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_bot=0 AND is_owner=0"
        ).fetchone()[0]
        total_page_views = conn.execute(
            "SELECT COUNT(*) FROM page_views"
        ).fetchone()[0]
        unique_ips = conn.execute(
            "SELECT COUNT(DISTINCT ip) FROM visitor_log WHERE is_bot=0 AND is_owner=0"
        ).fetchone()[0]
        bot_count = conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_bot=1"
        ).fetchone()[0]
        human_count = conn.execute(
            "SELECT COUNT(*) FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND human_score >= 60"
        ).fetchone()[0]
        owner_count = conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_owner=1"
        ).fetchone()[0]
        avg_score = conn.execute(
            "SELECT ROUND(AVG(human_score),1) FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND human_score >= 0"
        ).fetchone()[0]

        top_pages = conn.execute(
            "SELECT path, COUNT(*) as cnt FROM page_views "
            "WHERE path NOT LIKE '/static%' "
            "GROUP BY path ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        # PASS 27 — Normalize NL duplicate at query time.
        top_countries = conn.execute(
            "SELECT CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country, "
            "country_code, COUNT(*) as cnt FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND country != 'Unknown' "
            "GROUP BY CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END, country_code "
            "ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        owner_visits = conn.execute(
            "SELECT ip, country, city, isp, MAX(visited_at) as last_visit, COUNT(*) as sessions "
            "FROM visitor_log WHERE is_owner=1 GROUP BY ip "
            "ORDER BY last_visit DESC LIMIT 20"
        ).fetchall()
        conn.close()

        human_pct = round(100 * human_count / max(1, total_sessions), 1)
        bot_pct = round(100 * bot_count / max(1, total_sessions + bot_count), 1)
        return jsonify({
            "total_sessions": int(total_sessions),
            "total_page_views": int(total_page_views),
            "unique_ips": int(unique_ips),
            "bot_count": int(bot_count),
            "human_count": int(human_count),
            "owner_count": int(owner_count),
            "human_pct": float(human_pct),
            "bot_pct": float(bot_pct),
            "avg_human_score": float(avg_score or 0),
            "top_pages": [{"path": r["path"], "count": r["cnt"]} for r in top_pages],
            "top_countries": [
                {"country": r["country"], "code": r["country_code"], "count": r["cnt"]}
                for r in top_countries
            ],
            "owner_visits": [
                {"ip": r["ip"], "country": r["country"], "city": r["city"],
                 "isp": r["isp"], "last_visit": r["last_visit"],
                 "sessions": r["sessions"]}
                for r in owner_visits
            ],
        })
    except Exception as e:
        log.warning("api_analytics_summary: %s", e)
        return jsonify({"error": str(e)}), 500


# ── PASS 12 — Visitors globe + stream + log + geo + stats ─────────────
@bp.route("/api/visitors/globe-data")
def api_visitors_globe_data():
    """Points carte (Leaflet) pour /visiteurs-live — agrégation par pays."""
    from station_web import get_global_stats
    try:
        exclude_my_ip = (request.args.get("exclude_my_ip", "1") or "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        p = get_global_stats(exclude_my_ip=exclude_my_ip)
        return jsonify({"ok": True, "points": p.get("points") or []})
    except Exception as e:
        log.warning("visitors/globe-data: %s", e)
        return jsonify({"ok": False, "points": [], "error": str(e)})


@bp.route("/api/visitors/stream")
def api_visitors_stream():
    """SSE : stats live pour la page Visiteurs LIVE."""
    import json as _json
    import time as _time
    from flask import Response
    from station_web import get_global_stats

    exclude_my_ip = (request.args.get("exclude_my_ip", "1") or "0").strip().lower() in (
        "1", "true", "yes", "on",
    )

    def gen():
        while True:
            try:
                payload = get_global_stats(exclude_my_ip=exclude_my_ip)
                yield f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as e:
                err = {
                    "error": str(e), "total": 0, "online_now": 0,
                    "top_countries": [], "last_connections": [],
                    "heatmap": [], "humans_total": 0,
                    "bots_total": 0, "humans_today": 0,
                }
                yield f"data: {_json.dumps(err, ensure_ascii=False)}\n\n"
            yield ": keepalive\n\n"
            _time.sleep(8)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@bp.route("/api/visitors/log", methods=["POST"])
def api_log_visitor():
    """Log un visiteur depuis le frontend."""
    from station_web import _register_unique_visit_from_request
    try:
        data = request.get_json(silent=True) or {}
        path = data.get("path", "/")
        tracked = _register_unique_visit_from_request(path_override=path)
        return jsonify({"ok": True, "tracked": bool(tracked)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@bp.route("/api/visitors/geo")
def api_visitors_geo():
    """Retourne les derniers visiteurs avec géolocalisation live (résolution ip-api.com)."""
    import requests as _req
    from station_web import _get_db_visitors
    try:
        my_ip = "105.235.139.99"
        exclude_my_ip = (request.args.get("exclude_my_ip", "0") or "0").strip() in (
            "1", "true", "yes", "on",
        )
        excluded = {"127.0.0.1", "::1"}
        if exclude_my_ip:
            excluded.add(my_ip)
        placeholders = ",".join(["?"] * len(excluded))
        params = tuple(excluded)
        conn = _get_db_visitors()
        rows = conn.execute(
            "SELECT id, ip, country, country_code, city, region, flag, path, visited_at "
            "FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) "
            "ORDER BY id DESC LIMIT 50",
            params,
        ).fetchall()
        conn.close()
        visitors = []
        ips_to_resolve = []
        for row in rows:
            v = {
                "id": row[0], "ip": row[1], "country": row[2],
                "country_code": row[3], "city": row[4], "region": row[5],
                "flag": row[6], "path": row[7], "visited_at": row[8],
            }
            if v["country"] == "Unknown" and v["ip"] not in ("127.0.0.1", "::1"):
                ips_to_resolve.append(v["ip"])
            visitors.append(v)

        resolved = {}
        unique_ips = list(set(ips_to_resolve))[:10]
        for ip in unique_ips:
            try:
                r = _req.get(
                    f"http://ip-api.com/json/{ip}"
                    f"?fields=status,country,countryCode,city,regionName",
                    timeout=3,
                )
                d = r.json()
                if d.get("status") == "success":
                    code = d.get("countryCode", "XX")
                    resolved[ip] = {
                        "country": d.get("country", "Unknown"),
                        "country_code": code,
                        "city": d.get("city", "Unknown"),
                        "region": d.get("regionName", "Unknown"),
                        "flag": code,
                    }
            except Exception:
                pass

        if resolved:
            conn2 = _get_db_visitors()
            for ip, geo in resolved.items():
                conn2.execute(
                    "UPDATE visitor_log SET country=?, country_code=?, city=?, "
                    "region=?, flag=? WHERE ip=? AND country='Unknown'",
                    (geo["country"], geo["country_code"], geo["city"],
                     geo["region"], geo["flag"], ip),
                )
            conn2.commit()
            conn2.close()
            for v in visitors:
                if v["ip"] in resolved:
                    v.update(resolved[v["ip"]])

        return jsonify({"visitors": visitors, "total": len(visitors)})
    except Exception as e:
        return jsonify({"visitors": [], "error": str(e)})


@bp.route("/api/visitors/stats")
def api_visitors_stats():
    """Statistiques visiteurs par pays."""
    from station_web import _get_db_visitors
    try:
        my_ip = "105.235.139.99"
        exclude_my_ip = (request.args.get("exclude_my_ip", "0") or "0").strip() in (
            "1", "true", "yes", "on",
        )
        excluded = {"127.0.0.1", "::1"}
        if exclude_my_ip:
            excluded.add(my_ip)
        placeholders = ",".join(["?"] * len(excluded))
        params = tuple(excluded)
        conn = _get_db_visitors()
        # PASS 27 — Normalize NL duplicate at query time.
        by_country = conn.execute(
            "SELECT CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country, "
            "country_code, COUNT(*) as cnt "
            "FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) AND country != 'Unknown' "
            "GROUP BY CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END, country_code "
            "ORDER BY cnt DESC LIMIT 50",
            params,
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM visitor_log WHERE ip NOT IN ({placeholders})",
            params,
        ).fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) AND date(visited_at)=date('now')",
            params,
        ).fetchone()[0]
        conn.close()
        return jsonify({
            "total": total,
            "today": today,
            "exclude_my_ip": exclude_my_ip,
            "by_country": [
                {"country": r[0], "code": r[1] or "XX", "count": r[2]}
                for r in by_country
                if (r[1] or "XX").upper() != "XX"
                and "inconnu" not in (r[0] or "").lower()
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ── PASS 12 — Track time (page duration beacon) ───────────────────────
@bp.route("/track-time", methods=["POST"])
def track_time_endpoint():
    """Enregistre la durée passée sur une page pour une session."""
    from datetime import datetime, timezone
    try:
        data = request.get_json(silent=True) or {}
        sid = (data.get("session_id") or request.cookies.get("astroscan_sid") or "")[:128]
        path = (data.get("path") or "")[:500]
        try:
            duration = int(data.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0
        if duration < 0:
            duration = 0
        if duration > 86400:
            duration = 86400
        if not sid:
            return jsonify({"ok": False, "error": "no session"}), 400
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO session_time (session_id, path, duration, created_at) "
            "VALUES (?, ?, ?, ?)",
            (sid, path, duration, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"ok": False}), 500


# ── PASS 16 — /api/visitors/connection_time (différé PASS 12 levé) ────
@bp.route("/api/visitors/connection_time")
def api_visitors_connection_time():
    """Temps de connexion par IP (visiteurs externes), dédupliqué et plafonné."""
    import os
    from datetime import datetime
    from station_web import _get_db_visitors
    try:
        def _parse_visitor_at(ts):
            s = (ts or "").strip()
            if not s:
                return None
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            if "T" in s:
                try:
                    return datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:
                    pass
            try:
                return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return None

        fallback_my_ip = "105.235.139.99"
        env_owner_ips = (os.environ.get("ASTROSCAN_OWNER_IPS") or "").strip()
        if env_owner_ips:
            owner_ips = {x.strip() for x in env_owner_ips.split(",") if x.strip()}
        else:
            owner_ips = set()
        single_owner = (os.environ.get("ASTROSCAN_MY_IP") or "").strip()
        if single_owner:
            owner_ips.add(single_owner)
        if not owner_ips:
            owner_ips.add(fallback_my_ip)

        related_owner_ips = set()
        try:
            conn_owner = _get_db_visitors()
            conn_owner.row_factory = sqlite3.Row
            owner_list = sorted(owner_ips)
            owner_ph = ",".join(["?"] * len(owner_list))
            sid_rows = conn_owner.execute(
                "SELECT DISTINCT session_id FROM visitor_log "
                f"WHERE ip IN ({owner_ph}) AND COALESCE(session_id,'')<>''",
                tuple(owner_list),
            ).fetchall()
            sids = [str(r["session_id"]).strip() for r in sid_rows if r["session_id"]]
            if sids:
                sid_ph = ",".join(["?"] * len(sids))
                ip_rows = conn_owner.execute(
                    "SELECT DISTINCT ip FROM visitor_log "
                    f"WHERE session_id IN ({sid_ph}) AND COALESCE(ip,'')<>''",
                    tuple(sids),
                ).fetchall()
                for r in ip_rows:
                    ip = str(r["ip"]).strip()
                    if ip:
                        related_owner_ips.add(ip)
            conn_owner.close()
        except Exception:
            related_owner_ips = set()
        effective_owner_ips = set(owner_ips) | set(related_owner_ips)
        exclude_my_ip = (request.args.get("exclude_my_ip", "0") or "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        excluded = {"127.0.0.1", "::1"}
        if exclude_my_ip:
            excluded.update(effective_owner_ips)
        placeholders = ",".join(["?"] * len(excluded))
        base_params = tuple(excluded)

        conn = _get_db_visitors()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ip, "
            "COALESCE(country,'Unknown') AS country, "
            "COALESCE(city,'Unknown') AS city, "
            "COALESCE(country_code,'XX') AS country_code, "
            "COALESCE(session_id,'') AS session_id, "
            "COALESCE(visited_at,'') AS visited_at "
            "FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) "
            "ORDER BY id DESC",
            base_params,
        ).fetchall()

        by_ip = {}
        session_ip_hits = {}
        for r in rows:
            ip = (r["ip"] or "").strip()
            if not ip:
                continue
            entry = by_ip.get(ip)
            vis_at = (r["visited_at"] or "").strip()
            if not entry:
                entry = {
                    "ip": ip,
                    "country": r["country"] or "Unknown",
                    "city": r["city"] or "Unknown",
                    "country_code": r["country_code"] or "XX",
                    "sessions": set(),
                    "session_count": 0,
                    "total_sec": 0,
                    "last_visit": vis_at,
                    "first_visit": vis_at,
                    "visit_count": 0,
                }
                by_ip[ip] = entry
            else:
                if vis_at and (not entry["last_visit"] or vis_at > entry["last_visit"]):
                    entry["last_visit"] = vis_at
                if vis_at and (not entry.get("first_visit") or vis_at < entry["first_visit"]):
                    entry["first_visit"] = vis_at
            entry["visit_count"] = int(entry.get("visit_count") or 0) + 1
            sid = (r["session_id"] or "").strip()
            if sid:
                entry["sessions"].add(sid)
                hit_map = session_ip_hits.get(sid)
                if not hit_map:
                    hit_map = {}
                    session_ip_hits[sid] = hit_map
                hit_map[ip] = int(hit_map.get(ip, 0)) + 1

        all_sids = list(session_ip_hits.keys())
        sid_totals = {}
        if all_sids:
            chunk = 500
            for i in range(0, len(all_sids), chunk):
                batch = all_sids[i: i + chunk]
                sid_ph = ",".join(["?"] * len(batch))
                t_rows = conn.execute(
                    "SELECT session_id, "
                    "COALESCE(SUM(duration),0) AS total_duration, "
                    "MIN(created_at) AS first_at, "
                    "MAX(created_at) AS last_at "
                    "FROM session_time "
                    f"WHERE session_id IN ({sid_ph}) "
                    "GROUP BY session_id",
                    tuple(batch),
                ).fetchall()
                for tr in t_rows:
                    sid = (tr["session_id"] or "").strip()
                    if not sid:
                        continue
                    total_sec = int(tr["total_duration"] or 0)
                    span_sec = 0
                    if tr["first_at"] and tr["last_at"]:
                        try:
                            dt0 = datetime.fromisoformat(str(tr["first_at"]).replace("Z", "+00:00"))
                            dt1 = datetime.fromisoformat(str(tr["last_at"]).replace("Z", "+00:00"))
                            span_sec = max(0, int((dt1 - dt0).total_seconds()))
                        except Exception:
                            span_sec = 0
                    if span_sec > 0:
                        total_sec = min(total_sec, span_sec)
                    sid_totals[sid] = max(0, min(total_sec, 86400 * 7))

        for entry in by_ip.values():
            sc = len(entry["sessions"])
            if sc <= 0 and int(entry.get("visit_count") or 0) > 0:
                sc = 1
            entry["session_count"] = sc
            entry["total_sec"] = 0

        for sid, hit_map in session_ip_hits.items():
            total = int(sid_totals.get(sid, 0))
            if total <= 0:
                continue
            denom = sum(int(v or 0) for v in hit_map.values())
            if denom <= 0:
                continue
            allocated = 0
            keys = list(hit_map.keys())
            for idx, ip in enumerate(keys):
                share = int(round(total * (int(hit_map[ip]) / float(denom))))
                if idx == len(keys) - 1:
                    share = max(0, total - allocated)
                allocated += share
                if ip in by_ip:
                    by_ip[ip]["total_sec"] += max(0, share)

        for entry in by_ip.values():
            if int(entry.get("total_sec") or 0) > 0:
                continue
            fv = entry.get("first_visit") or ""
            lv = entry.get("last_visit") or ""
            dt0 = _parse_visitor_at(fv)
            dt1 = _parse_visitor_at(lv)
            if dt0 and dt1:
                est = max(0, int((dt1 - dt0).total_seconds()))
                if est <= 0 and int(entry.get("visit_count") or 0) > 0:
                    est = 1
                entry["total_sec"] = min(est, 86400 * 7)

        conn.close()

        def _fmt_duration(sec):
            sec = int(sec or 0)
            h, rem = divmod(sec, 3600)
            m, s = divmod(rem, 60)
            if h > 0:
                return f"{h}h{m:02d}m{s:02d}"
            if m > 0:
                return f"{m} min {s} s"
            return f"{s} s"

        def _level(sec):
            if sec >= 180:
                return "FORT"
            if sec >= 30:
                return "MOYEN"
            return "FAIBLE"

        items = []
        for v in by_ip.values():
            is_my_ip = False if exclude_my_ip else (v["ip"] in effective_owner_ips)
            items.append({
                "ip": v["ip"],
                "country": v["country"],
                "city": v["city"],
                "country_code": v["country_code"],
                "sessions": v["session_count"],
                "total_sec": v["total_sec"],
                "total_time": _fmt_duration(v["total_sec"]),
                "level": _level(v["total_sec"]),
                "last_visit": v["last_visit"],
                "is_my_ip": is_my_ip,
                "traffic_segment": "owner_test" if is_my_ip else "external_visitor",
            })

        items.sort(
            key=lambda x: (x.get("last_visit") or "", x["total_sec"], x["sessions"]),
            reverse=True,
        )
        my_items = [x for x in items if x.get("is_my_ip")]
        ext_items = [x for x in items if not x.get("is_my_ip")]
        my_total_sec = sum(int(x.get("total_sec") or 0) for x in my_items)
        ext_total_sec = sum(int(x.get("total_sec") or 0) for x in ext_items)
        resp = jsonify({
            "ok": True,
            "exclude_my_ip": exclude_my_ip,
            "my_ip": sorted(owner_ips)[0] if owner_ips else fallback_my_ip,
            "owner_ips": sorted(owner_ips),
            "effective_owner_ips": sorted(effective_owner_ips),
            "total_ips": len(items),
            "my_ip_count": len(my_items),
            "external_ip_count": len(ext_items),
            "my_total_sec": my_total_sec,
            "external_total_sec": ext_total_sec,
            "items": items[:100],
        })
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "items": []}), 500


# ── PASS 16 — /analytics dashboard page (différé PASS 12 levé) ────────
@bp.route("/analytics")
def analytics_dashboard():
    """Dashboard analytics complet : sessions, page_views, human_score, owner IPs."""
    from station_web import _get_db_visitors
    from app.services.analytics_dashboard import (
        load_analytics_readonly, analytics_empty_payload,
    )
    try:
        data = load_analytics_readonly()
    except Exception:
        data = analytics_empty_payload()

    total_page_views = 0
    human_count = 0
    suspect_count = 0
    top_pages = []
    owner_visits = []
    db_ips = []
    env_ips = [
        x.strip()
        for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(",")
        if x.strip()
    ]
    avg_human_score = 0.0
    try:
        conn = _get_db_visitors()
        conn.row_factory = sqlite3.Row

        total_page_views = (
            conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0] or 0
        )

        human_count = (conn.execute(
            "SELECT COUNT(*) FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND human_score >= 60"
        ).fetchone()[0] or 0)
        suspect_count = (conn.execute(
            "SELECT COUNT(*) FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND human_score >= 20 AND human_score < 60"
        ).fetchone()[0] or 0)
        avg_row = conn.execute(
            "SELECT ROUND(AVG(human_score),1) FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND human_score >= 0"
        ).fetchone()
        avg_human_score = float(avg_row[0] or 0)

        top_page_rows = conn.execute(
            "SELECT path, COUNT(*) as cnt FROM page_views "
            "WHERE path NOT LIKE '/static%' "
            "GROUP BY path ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        top_pages = [{"path": r["path"], "count": r["cnt"]} for r in top_page_rows]

        ov_rows = conn.execute(
            "SELECT ip, COALESCE(country,'?') as country, COALESCE(city,'?') as city, "
            "COALESCE(isp,'') as isp, MAX(visited_at) as last_visit, COUNT(*) as sessions "
            "FROM visitor_log WHERE is_owner=1 GROUP BY ip "
            "ORDER BY last_visit DESC LIMIT 20"
        ).fetchall()
        owner_visits = [dict(r) for r in ov_rows]

        city_rows = conn.execute(
            "SELECT country, city, COALESCE(region,'') as region, "
            "COALESCE(isp,'') as isp, COUNT(*) as cnt "
            "FROM visitor_log WHERE is_bot=0 AND is_owner=0 "
            "AND city != 'Unknown' AND city != '' "
            "GROUP BY city ORDER BY cnt DESC LIMIT 15"
        ).fetchall()
        data["top_cities"] = [
            {"country": r["country"], "city": r["city"], "region": r["region"],
             "isp": r["isp"], "count": r["cnt"]}
            for r in city_rows
        ]

        last_rows = conn.execute(
            "SELECT ip, country, city, path, visited_at, isp, "
            "human_score, is_bot, is_owner "
            "FROM visitor_log ORDER BY id DESC LIMIT 30"
        ).fetchall()
        data["latest_visits"] = [dict(r) for r in last_rows]

        for block in data.get("sessions_timeline", []):
            try:
                ip = block.get("ip", "")
                if ip:
                    vrow = conn.execute(
                        "SELECT isp, human_score FROM visitor_log WHERE ip=? LIMIT 1",
                        (ip,),
                    ).fetchone()
                    block["isp"] = vrow["isp"] if vrow else ""
                    block["human_score"] = int(vrow["human_score"] or -1) if vrow else -1
                else:
                    block["isp"] = ""
                    block["human_score"] = -1
            except Exception:
                block["isp"] = ""
                block["human_score"] = -1

        db_ip_rows = conn.execute(
            "SELECT id, ip, label, added_at FROM owner_ips ORDER BY added_at DESC"
        ).fetchall()
        db_ips = [dict(r) for r in db_ip_rows]

        conn.close()
    except Exception as ex:
        log.warning("analytics_dashboard extra: %s", ex)

    bot_count = data.get("bot_count", 0)
    if not bot_count:
        try:
            conn2 = _get_db_visitors()
            bot_count = (conn2.execute(
                "SELECT COUNT(*) FROM visitor_log WHERE is_bot=1"
            ).fetchone()[0] or 0)
            conn2.close()
        except Exception:
            bot_count = 0

    return render_template(
        "analytics.html",
        total_visits=data.get("total_visits", 0),
        unique_ips=data.get("unique_ips", 0),
        total_tracked_events=data.get("total_tracked_events", 0),
        last_activity=data.get("last_activity", "—"),
        total_sessions=data.get("total_visits", 0),
        total_page_views=int(total_page_views),
        human_count=int(human_count),
        suspect_count=int(suspect_count),
        bot_count=int(bot_count),
        human_pct=round(100 * human_count / max(1, data.get("total_visits", 1)), 1),
        avg_human_score=round(avg_human_score, 1),
        owner_count=len(owner_visits),
        top_pages=top_pages,
        top_countries=data.get("top_countries", []),
        top_cities=data.get("top_cities", []),
        top_pages_by_time=data.get("top_pages_by_time", []),
        avg_duration_by_page=data.get("avg_duration_by_page", []),
        latest_visits=data.get("latest_visits", []),
        sessions_timeline=data.get("sessions_timeline", []),
        session_visitors_detail=data.get("session_visitors_detail", []),
        owner_visits=owner_visits,
        db_ips=db_ips,
        env_ips=env_ips,
    )
