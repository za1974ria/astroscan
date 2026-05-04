"""Service centralisé pour les statistiques visiteurs / pays AstroScan.

Extrait de station_web.py — source unique de vérité pour :
  • comptage visiteurs (total, humains, aujourd'hui)
  • pays distincts, top pays, heatmap continents
  • points carte (centroides), dernières connexions
"""

import os
import re
import sqlite3
import time
from datetime import datetime


DB_VISITORS_PATH = "/root/astro_scan/data/archive_stellaire.db"

_visitor_bot_re = re.compile(
    r"bot|crawl|spider|slurp|bingpreview|facebookexternal|semrush|ahrefs|"
    r"curl/|wget|python-requests|axios|go-http|http\.client|libwww|scrapy|"
    r"googlebot|bingbot|yandex|duckduck|baiduspider|petalbot|applebot|gptbot|"
    r"claudebot|anthropic|bytespider",
    re.I,
)

_CC_CENTROID = {
    "FR": (46.6034, 1.8883), "US": (39.8283, -98.5795), "DZ": (28.0339, 1.6596),
    "DE": (51.1657, 10.4515), "GB": (54.7023, -3.2766), "RU": (61.524, 105.3188),
    "CN": (35.8617, 104.1954), "JP": (36.2048, 138.2529), "BR": (-14.235, -51.9253),
    "IN": (20.5937, 78.9629), "CA": (56.1304, -106.3468), "AU": (-25.2744, 133.7751),
    "IT": (41.8719, 12.5674), "ES": (40.4637, -3.7492), "NL": (52.1326, 5.2913),
    "BE": (50.5039, 4.4699), "CH": (46.8182, 8.2275), "AT": (47.5162, 14.5501),
    "PL": (51.9194, 19.1451), "SE": (60.1282, 18.6435), "NO": (60.472, 8.4689),
    "FI": (61.9241, 25.7482), "DK": (56.2639, 9.5018), "PT": (39.3999, -8.2245),
    "GR": (39.0742, 21.8243), "TR": (38.9637, 35.2433), "SA": (23.8859, 45.0792),
    "AE": (23.4241, 53.8478), "IL": (31.0461, 34.8516), "EG": (26.8206, 30.8025),
    "ZA": (-30.5595, 22.9375), "NG": (9.082, 8.6753), "MX": (23.6345, -102.5528),
    "AR": (-38.4161, -63.6167), "CL": (-35.6751, -71.543), "CO": (4.5709, -74.2973),
    "KR": (35.9078, 127.7669), "TW": (23.6978, 120.9605), "SG": (1.3521, 103.8198),
    "MY": (4.2105, 101.9758), "TH": (15.87, 100.9925), "VN": (14.0583, 108.2772),
    "PH": (12.8797, 121.774), "ID": (-0.7893, 113.9213), "NZ": (-40.9006, 174.886),
    "IE": (53.4129, -8.2439), "CZ": (49.8175, 15.473), "RO": (45.9432, 24.9668),
    "HU": (47.1625, 19.5033), "UA": (48.3794, 31.1656), "MA": (31.7917, -7.0926),
    "TN": (33.8869, 9.5375), "SN": (14.4974, -14.4524),
}

_CC_TO_CONTINENT = {
    "US": "Amériques", "CA": "Amériques", "MX": "Amériques", "BR": "Amériques",
    "AR": "Amériques", "CL": "Amériques", "CO": "Amériques", "PE": "Amériques",
    "FR": "Europe", "DE": "Europe", "GB": "Europe", "IT": "Europe", "ES": "Europe",
    "NL": "Europe", "BE": "Europe", "CH": "Europe", "AT": "Europe", "PL": "Europe",
    "SE": "Europe", "NO": "Europe", "FI": "Europe", "DK": "Europe", "PT": "Europe",
    "GR": "Europe", "IE": "Europe", "CZ": "Europe", "RO": "Europe", "HU": "Europe",
    "UA": "Europe", "RU": "Europe", "TR": "Europe", "DZ": "Afrique", "MA": "Afrique",
    "TN": "Afrique", "NG": "Afrique", "SN": "Afrique", "ZA": "Afrique", "EG": "Afrique",
    "CN": "Asie", "JP": "Asie", "KR": "Asie", "IN": "Asie", "SG": "Asie", "TH": "Asie",
    "VN": "Asie", "PH": "Asie", "ID": "Asie", "MY": "Asie", "TW": "Asie", "IL": "Asie",
    "AE": "Asie", "SA": "Asie", "AU": "Océanie", "NZ": "Océanie",
}


def _get_db():
    return sqlite3.connect(DB_VISITORS_PATH)


def _excluded_ips(exclude_my_ip):
    excluded = {"127.0.0.1", "::1"}
    if not exclude_my_ip:
        return excluded
    for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(","):
        x = x.strip()
        if x:
            excluded.add(x)
    single = (os.environ.get("ASTROSCAN_MY_IP") or "").strip()
    if single:
        excluded.add(single)
    excluded.add("105.235.139.99")
    return excluded


def _visited_at_to_unix(ts):
    if not ts:
        return None
    s = str(ts).strip()
    try:
        if "T" in s:
            return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
        return int(datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").timestamp())
    except Exception:
        return None


def get_global_stats(exclude_my_ip=True):
    """Payload complet stats visiteurs — source unique utilisée par toutes les pages."""
    excluded = _excluded_ips(exclude_my_ip)
    ph = ",".join(["?"] * len(excluded))
    params = tuple(excluded)

    online_now = 0
    today_h = 0
    by_country = []
    last_rows = []
    gcc = []
    agg = []

    conn = _get_db()
    try:
        rows = conn.execute(
            f"SELECT ip, user_agent, country, country_code, city, visited_at "
            f"FROM visitor_log WHERE ip NOT IN ({ph}) ORDER BY id DESC LIMIT 8000",
            params,
        ).fetchall()

        try:
            online_row = conn.execute(
                f"SELECT COUNT(DISTINCT ip) FROM visitor_log WHERE ip NOT IN ({ph}) "
                f"AND datetime(replace(visited_at,'T',' ')) >= datetime('now','-5 minutes')",
                params,
            ).fetchone()
            online_now = int(online_row[0] or 0)
        except Exception:
            online_now = 0

        today_uas = conn.execute(
            f"SELECT user_agent FROM visitor_log WHERE ip NOT IN ({ph}) "
            f"AND date(visited_at)=date('now') LIMIT 20000",
            params,
        ).fetchall()
        for (ua,) in today_uas:
            if not _visitor_bot_re.search((ua or "")[:400]):
                today_h += 1

        # PASS 27 — Normalize NL duplicate (Netherlands / The Netherlands) at query time.
        by_country = conn.execute(
            f"SELECT CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country, "
            f"country_code, COUNT(*) as cnt FROM visitor_log "
            f"WHERE ip NOT IN ({ph}) AND COALESCE(country,'')<>'' AND country<>'Unknown' "
            f"GROUP BY CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END, country_code "
            f"ORDER BY cnt DESC LIMIT 50",
            params,
        ).fetchall()

        last_rows = conn.execute(
            f"SELECT country, country_code, city, visited_at FROM visitor_log "
            f"WHERE ip NOT IN ({ph}) ORDER BY id DESC LIMIT 18",
            params,
        ).fetchall()

        gcc = conn.execute(
            f"SELECT country_code, COUNT(*) as cnt FROM visitor_log "
            f"WHERE ip NOT IN ({ph}) AND COALESCE(country_code,'')<>'' "
            f"GROUP BY country_code",
            params,
        ).fetchall()

        agg = conn.execute(
            f"SELECT country_code, MAX(country) as cname, COUNT(*) as cnt FROM visitor_log "
            f"WHERE ip NOT IN ({ph}) AND COALESCE(country_code,'')<>'' "
            f"GROUP BY country_code",
            params,
        ).fetchall()
    finally:
        conn.close()

    humans = bots = 0
    for _ip, ua, _c, _cc, _ci, _v in rows:
        ua = (ua or "")[:400]
        if _visitor_bot_re.search(ua):
            bots += 1
        else:
            humans += 1

    total_all = humans + bots
    human_pct = round(100.0 * humans / total_all) if total_all else 0

    heatmap_acc = {}
    for code, cnt in gcc:
        cc = (code or "XX").upper()
        cont = _CC_TO_CONTINENT.get(cc, "Autres / océan")
        heatmap_acc[cont] = heatmap_acc.get(cont, 0) + int(cnt)

    top_countries = [
        {"country": r[0], "code": (r[1] or "XX")[:2], "count": r[2]}
        for r in by_country
        if (r[1] or "XX").upper() != "XX" and "inconnu" not in (r[0] or "").lower()
    ]

    last_connections = []
    for country, code, city, visited_at in last_rows:
        ts = _visited_at_to_unix(visited_at)
        last_connections.append({
            "country": country or "",
            "code": (code or "XX")[:2],
            "city": city or "",
            "timestamp": ts or int(time.time()),
        })

    heatmap = [{"continent": k, "count": v} for k, v in sorted(
        heatmap_acc.items(), key=lambda x: -x[1]
    )]

    points = []
    for code, cname, cnt in agg:
        cc = (code or "").upper()[:2]
        if cc == "XX" or not cc:
            continue
        ll = _CC_CENTROID.get(cc)
        if not ll:
            continue
        lat, lon = ll
        points.append({
            "lat": lat, "lon": lon, "count": int(cnt),
            "country": cname or cc, "code": cc,
        })

    return {
        "total": total_all,
        "online_now": online_now,
        "top_countries": top_countries,
        "distinct_countries": len(gcc),
        "last_connections": last_connections,
        "heatmap": heatmap,
        "humans_total": humans,
        "bots_total": bots,
        "humans_today": int(today_h),
        "human_pct_display": human_pct,
        "points": points,
    }


def get_top_countries(exclude_my_ip=True):
    return get_global_stats(exclude_my_ip)["top_countries"]


def get_today_visitors(exclude_my_ip=True):
    return get_global_stats(exclude_my_ip)["humans_today"]


def get_distinct_countries(exclude_my_ip=True):
    return get_global_stats(exclude_my_ip)["distinct_countries"]
