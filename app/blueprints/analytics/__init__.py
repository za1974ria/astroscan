"""Blueprint Analytics — endpoints de tracking visiteurs.

Endpoints :
  - /api/visits             (GET)  : compteur actuel
  - /api/visits/increment   (POST) : incremente et retourne nouvelle valeur
  - /api/visits/reset       (POST) : reset compteur (admin)
  - /api/visits/count       (GET)  : compteur direct via SQLite

Migration depuis station_web.py (CTO Critique 3 - Monolith reduction).
"""

import logging
import sqlite3

from flask import Blueprint, jsonify, redirect, request

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
        top_countries = conn.execute(
            "SELECT country, country_code, COUNT(*) as cnt FROM visitor_log "
            "WHERE is_bot=0 AND is_owner=0 AND country != 'Unknown' "
            "GROUP BY country ORDER BY cnt DESC LIMIT 10"
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
        by_country = conn.execute(
            "SELECT country, country_code, COUNT(*) as cnt "
            "FROM visitor_log "
            f"WHERE ip NOT IN ({placeholders}) AND country != 'Unknown' "
            "GROUP BY country, country_code "
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
