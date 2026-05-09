#!/usr/bin/env python3
import json
import re
from collections import Counter
from pathlib import Path
from urllib import parse, request


TARGET_TOKEN = "23/Apr/2026"
TARGET_DATE = "2026-04-23"
MAX_GEO_IPS = 50

NGINX_CANDIDATES = [
    Path("/var/log/nginx/access.log"),
    Path("/var/log/nginx/access.log.1"),
]

FALLBACK_CANDIDATES = [
    Path("/tmp/flask.log"),
    Path("/root/astro_scan/logs/web.log"),
]

BOT_MARKERS = ("bot", "crawler", "spider", "curl", "python-requests")

NGINX_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<route>\S+) [^"]+" (?P<status>\d{3}) \S+ '
    r'"[^"]*" "(?P<ua>[^"]*)"'
)


def pick_log_files():
    found = [p for p in NGINX_CANDIDATES if p.exists()]
    source = "nginx"
    if not found:
        found = [p for p in FALLBACK_CANDIDATES if p.exists()]
        source = "gunicorn_fallback"
    return source, found


def classify_user_agent(ua):
    text = (ua or "").lower()
    return "bot" if any(marker in text for marker in BOT_MARKERS) else "human"


def parse_line(line):
    m = NGINX_RE.match(line)
    if not m:
        return None
    route = m.group("route") or "/"
    route = parse.urlsplit(route).path or "/"
    return {
        "ip": m.group("ip"),
        "timestamp": m.group("ts"),
        "route": route,
        "user_agent": m.group("ua"),
    }


def geolocate_ip(ip):
    url = f"http://ip-api.com/json/{parse.quote(ip)}?fields=status,country,city"
    try:
        with request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        if data.get("status") == "success":
            return data.get("country") or "Unknown", data.get("city") or ""
    except Exception:
        pass
    return "Unknown", ""


def main():
    source, files = pick_log_files()
    if not files:
        payload = {
            "date": TARGET_DATE,
            "source": "none",
            "total_visits": 0,
            "unique_ips": 0,
            "humans": 0,
            "bots": 0,
            "countries": {},
            "top_routes": [],
            "sample_ips": [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("\nINTERPRETATION :")
        print("- Aucun log exploitable trouvé pour la date demandée.")
        return

    entries = []
    for path in files:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if TARGET_TOKEN not in line:
                    continue
                parsed = parse_line(line.strip())
                if parsed:
                    entries.append(parsed)

    route_counts = Counter()
    ip_seen = set()
    human_count = 0
    bot_count = 0

    for item in entries:
        route_counts[item["route"]] += 1
        ip_seen.add(item["ip"])
        actor_type = classify_user_agent(item["user_agent"])
        item["type"] = actor_type
        if actor_type == "bot":
            bot_count += 1
        else:
            human_count += 1

    geo_targets = list(ip_seen)[:MAX_GEO_IPS]
    geo_map = {}
    country_counts = Counter()
    for ip in geo_targets:
        country, city = geolocate_ip(ip)
        geo_map[ip] = {"country": country, "city": city}
        country_counts[country] += 1

    sample = []
    for item in entries[:20]:
        geo = geo_map.get(item["ip"], {"country": "Unknown", "city": ""})
        sample.append(
            {
                "ip": item["ip"],
                "type": item["type"],
                "country": geo["country"],
                "city": geo["city"],
                "route": item["route"],
            }
        )

    payload = {
        "date": TARGET_DATE,
        "source": source,
        "total_visits": len(entries),
        "unique_ips": len(ip_seen),
        "humans": human_count,
        "bots": bot_count,
        "countries": dict(country_counts.most_common()),
        "top_routes": [{"route": r, "count": c} for r, c in route_counts.most_common(10)],
        "sample_ips": sample,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\nINTERPRETATION :")
    if len(entries) < 200:
        trafic = "faible"
    elif len(entries) < 2000:
        trafic = "moyen"
    else:
        trafic = "actif"
    print(f"- Niveau de trafic: {trafic} ({len(entries)} requêtes).")
    print(
        f"- Répartition humain/bot: {human_count} humains vs {bot_count} bots "
        f"({(bot_count / len(entries) * 100):.1f}% bots)." if entries else "- Répartition humain/bot: aucune requête."
    )
    international = len([c for c in country_counts if c != "Unknown"])
    if international >= 3:
        print("- Présence internationale: oui (plusieurs pays détectés).")
    elif international >= 1:
        print("- Présence internationale: limitée (quelques pays détectés).")
    else:
        print("- Présence internationale: non déterminable (géolocalisation limitée).")
    if human_count > 0:
        print("- Intérêt réel détecté: oui, trafic humain observé.")
    else:
        print("- NOTE : bots actifs aujourd’hui → visibilité SEO en cours")


if __name__ == "__main__":
    main()
