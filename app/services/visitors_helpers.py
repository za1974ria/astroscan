"""PASS 20.1 (2026-05-08) — Façade unifiée des helpers visiteurs.

Ce module regroupe les 8 helpers liés aux visiteurs / géolocalisation IP /
statistiques globales sous un seul point d'import. Sept d'entre eux sont
des re-exports depuis leurs modules de résidence (déjà extraits lors de
PASS antérieurs) ; ``get_geo_from_ip`` est implémenté ici (extrait depuis
station_web.py PASS 20.1).

Le shim ``station_web`` ré-exporte ces noms pour la rétro-compatibilité
des imports existants ``from station_web import get_geo_from_ip``.
"""
from __future__ import annotations

import requests

from services.cache_service import cache_get, cache_set

# Re-exports depuis app/services/db_visitors.py (PASS antérieur)
from app.services.db_visitors import (
    _compute_human_score,
    _get_db_visitors,
    _get_visits_count,
    _increment_visits,
    _invalidate_owner_ips_cache,
    _register_unique_visit_from_request,
)

# Re-export depuis services/stats_service.py (PASS antérieur)
from services.stats_service import get_global_stats


def get_geo_from_ip(ip):
    """Géolocalisation complète via ip-api.com (cache 24 h) : pays, ville, région, ISP, lat/lon.
    Retourne {} si IP invalide ou échec. Fallback ipinfo.io si ip-api échoue."""
    if ip is None:
        return {}
    ip = str(ip).strip()
    if ip in ("", "—", "127.0.0.1", "::1"):
        return {"country": "Serveur local", "city": "Serveur local", "country_code": "LO", "isp": "localhost"}
    ip = ip.split(",")[0].strip()
    if not ip:
        return {}
    cache_key = f"geo_ip:{ip}"
    cached = cache_get(cache_key, 86400)
    if cached is not None:
        return cached
    out = {}
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,regionName,lat,lon,isp",
            timeout=3,
        )
        d = r.json()
        if d.get("status") == "success":
            out = {
                "country": d.get("country") or "Inconnu",
                "city": d.get("city") or "Inconnu",
                "country_code": (d.get("countryCode") or "XX").upper(),
                "region": d.get("regionName") or "Inconnu",
                "lat": d.get("lat"),
                "lon": d.get("lon"),
                "isp": d.get("isp") or "",
            }
    except Exception:
        pass
    if not out:
        # Fallback ipinfo.io si ip-api échoue ou rate-limit
        try:
            r2 = requests.get(f"https://ipinfo.io/{ip}/json", timeout=3)
            d2 = r2.json() if r2.ok else {}
            cc = (d2.get("country") or "").strip().upper()
            loc = (d2.get("loc") or "").split(",")
            out = {
                "country": d2.get("country_name") or d2.get("country") or "Inconnu",
                "city": d2.get("city") or "Inconnu",
                "country_code": cc or "XX",
                "region": d2.get("region") or "Inconnu",
                "lat": float(loc[0]) if len(loc) == 2 else None,
                "lon": float(loc[1]) if len(loc) == 2 else None,
                "isp": d2.get("org") or "",
            }
        except Exception:
            out = {}
    cache_set(cache_key, out)
    return out


__all__ = [
    "_compute_human_score",
    "_get_db_visitors",
    "_get_visits_count",
    "_increment_visits",
    "_invalidate_owner_ips_cache",
    "_register_unique_visit_from_request",
    "get_global_stats",
    "get_geo_from_ip",
]
