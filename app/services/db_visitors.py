"""Service db_visitors — connexion SQLite + helpers analytics visiteurs.

Extrait depuis station_web.py :
  - PASS 23 (2026-05-04) : `_get_db_visitors`
  - PASS 2D Cat 1 (2026-05-07) : `_get_visits_count`, `_increment_visits`,
    `_compute_human_score`, `_invalidate_owner_ips_cache`,
    `_register_unique_visit_from_request`, owner-IPs cluster
    (`_OWNER_IPS_CACHE`, `_OWNER_IPS_LOCK`, `_OWNER_IPS_CACHE_TS`,
    `_load_owner_ips`, `_is_owner_ip`).

station_web.py conserve un re-export des symboles publics pour la compat
des imports legacy (`from station_web import X`).
"""
import logging
import os
import secrets
import sqlite3 as _sqlite3
import threading
import time

from flask import g, request

from app.services.security import _client_ip_from_request
from services.utils import _is_bot_user_agent


log = logging.getLogger(__name__)

DB_PATH = "/root/astro_scan/data/archive_stellaire.db"


def _get_db_visitors():
    return _sqlite3.connect(DB_PATH)


def _get_visits_count():
    """Retourne le nombre actuel de visites."""
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    row = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()
    conn.close()
    return row[0] if row else 0


def _increment_visits():
    """Incrémente le compteur de visites et retourne la nouvelle valeur."""
    conn = _sqlite3.connect(DB_PATH)
    conn.execute("UPDATE visits SET count = count + 1 WHERE id=1")
    new_count = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()[0]
    conn.commit()
    conn.close()
    return new_count


# ── Owner IPs : cache in-memory rechargé toutes les 5 min ───────────────────
_OWNER_IPS_CACHE: set = set()
_OWNER_IPS_CACHE_TS: float = 0.0
_OWNER_IPS_LOCK = threading.Lock()


def _load_owner_ips() -> set:
    """Charge les IPs propriétaire depuis : env ASTROSCAN_OWNER_IPS + table owner_ips DB.
    Cache 5 min en mémoire pour éviter une requête DB à chaque requête HTTP."""
    global _OWNER_IPS_CACHE, _OWNER_IPS_CACHE_TS
    now = time.time()
    with _OWNER_IPS_LOCK:
        if now - _OWNER_IPS_CACHE_TS < 300 and _OWNER_IPS_CACHE:
            return set(_OWNER_IPS_CACHE)
        ips: set = set()
        # Depuis .env
        for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(","):
            x = x.strip()
            if x:
                ips.add(x)
        single = (os.environ.get("ASTROSCAN_MY_IP") or "").strip()
        if single:
            ips.add(single)
        # Depuis la table DB
        try:
            conn = _get_db_visitors()
            rows = conn.execute("SELECT ip FROM owner_ips").fetchall()
            conn.close()
            for r in rows:
                if r[0]:
                    ips.add(str(r[0]).strip())
        except Exception:
            pass
        _OWNER_IPS_CACHE = ips
        _OWNER_IPS_CACHE_TS = now
        return set(ips)


def _is_owner_ip(ip: str) -> bool:
    """Retourne True si l'IP appartient au propriétaire."""
    if not ip:
        return False
    return ip in _load_owner_ips()


def _invalidate_owner_ips_cache():
    """Force le rechargement du cache IPs propriétaire au prochain appel."""
    global _OWNER_IPS_CACHE_TS
    with _OWNER_IPS_LOCK:
        _OWNER_IPS_CACHE_TS = 0.0


def _compute_human_score(ua: str, page_count: int = 1, session_sec: int = 0,
                          referrer: str = "", js_beacon: bool = False) -> int:
    """Score humain 0-100 pour un visiteur.
    - UA bot connu → 0
    - UA vide ou générique → 20
    - Navigation multi-pages → +30
    - Temps sur site > 30s → +20
    - Référent valide → +10
    - JS beacon reçu → +20
    Score ≥ 60 = humain probable."""
    ua_clean = (ua or "").strip()
    if _is_bot_user_agent(ua_clean):
        return 0
    score = 20  # Base : UA non-bot
    if not ua_clean:
        score = 5
    elif len(ua_clean) < 15:
        score = 10
    if page_count > 1:
        score += 30
    if session_sec > 30:
        score += 20
    if referrer and referrer not in ("", "direct") and not referrer.startswith("https://astroscan.space"):
        score += 10
    if js_beacon:
        score += 20
    return min(100, score)


def _register_unique_visit_from_request(path_override=None):
    """Insère 1 visite par session (IP+session_id), page_views pour chaque vue de page.
    - Détecte is_owner, calcule human_score initial
    - ISP + lat/lon stockés depuis ip-api.com
    - INSERT OR IGNORE + UNIQUE INDEX = résistance totale race condition multi-workers."""
    # Lazy import : `get_geo_from_ip` reste dans station_web (deps requests +
    # cache_service). Sera extrait dans une session future.
    from station_web import get_geo_from_ip
    try:
        ip = _client_ip_from_request(request)
        if ip in ("", "0.0.0.0", "127.0.0.1", "::1"):
            return False
        ua = (request.headers.get("User-Agent") or "")[:200]
        sid = (
            getattr(g, "_astroscan_sid", None)
            or request.cookies.get("astroscan_sid")
            or secrets.token_urlsafe(16)
        )[:128]
        path = (path_override or request.path or "/")[:500]
        referrer = (request.headers.get("Referer") or "")[:500]
        is_bot = 1 if _is_bot_user_agent(ua) else 0
        is_owner = 1 if _is_owner_ip(ip) else 0

        conn = _get_db_visitors()
        cur = conn.cursor()

        # ── 1. Enregistrement page_views (chaque vue, y compris bots) ────────
        try:
            cur.execute(
                "INSERT INTO page_views (session_id, ip, path, referrer) VALUES (?, ?, ?, ?)",
                (sid, ip, path, referrer),
            )
        except Exception:
            pass

        # ── 2. Une seule entrée visitor_log par (ip, session_id) ─────────────
        exists = cur.execute(
            "SELECT 1 FROM visitor_log WHERE ip = ? AND session_id = ? LIMIT 1",
            (ip, sid),
        ).fetchone()
        if exists:
            # Session connue : mettre à jour human_score si nécessaire
            try:
                page_cnt = cur.execute(
                    "SELECT COUNT(*) FROM page_views WHERE session_id=? AND ip=?",
                    (sid, ip),
                ).fetchone()[0]
                score = _compute_human_score(ua, page_count=page_cnt, referrer=referrer)
                cur.execute(
                    "UPDATE visitor_log SET human_score=? WHERE ip=? AND session_id=?",
                    (score, ip, sid),
                )
            except Exception:
                pass
            conn.commit()
            conn.close()
            return False

        # Nouveau visiteur / nouvelle session — récupérer la géoloc
        if is_bot:
            geo = {}
        else:
            geo = get_geo_from_ip(ip)
        country = (geo.get("country") or "Inconnu")[:80]
        country_code = (geo.get("country_code") or "XX")[:8]
        city = (geo.get("city") or "Inconnu")[:120]
        region = (geo.get("region") or "Inconnu")[:120]
        isp = (geo.get("isp") or "")[:200]
        lat = geo.get("lat")
        lon = geo.get("lon")
        score = _compute_human_score(ua, page_count=1, referrer=referrer)

        # INSERT OR IGNORE : sécurité race condition
        cur.execute(
            """
            INSERT OR IGNORE INTO visitor_log (
                ip, user_agent, path, session_id,
                country, country_code, city, region, flag,
                is_bot, is_owner, isp, lat, lon, human_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ip, ua, path, sid,
             country, country_code, city, region, country_code,
             is_bot, is_owner, isp, lat, lon, score),
        )
        if cur.rowcount > 0 and not is_bot and not is_owner:
            cur.execute("UPDATE visits SET count = count + 1 WHERE id=1")
        conn.commit()
        conn.close()
        return cur.rowcount > 0
    except Exception as e:
        log.warning("register unique visit: %s", e)
        return False
