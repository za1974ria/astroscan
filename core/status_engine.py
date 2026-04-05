"""
Agrégation défensive d’indicateurs opérationnels (santé, fraîcheur TLE, Redis, SQLite).
Appelé par station_web de façon optionnelle — aucune dépendance circulaire vers l’app Flask.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_age_seconds(iso_str: Optional[str]) -> Optional[int]:
    if not iso_str or not isinstance(iso_str, str):
        return None
    s = iso_str.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    except Exception:
        return None


def probe_sqlite(db_path: str, timeout: float = 5.0) -> str:
    try:
        p = Path(db_path)
        if not p.is_file():
            return "error"
        conn = sqlite3.connect(db_path, timeout=timeout)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return "ok"
    except Exception:
        return "error"


def probe_redis(url: Optional[str] = None) -> str:
    """
    Retourne connected | absent | error | unavailable
    (unavailable = module redis absent ; absent = pas d’URL configurée)
    """
    try:
        import redis  # type: ignore
    except Exception:
        return "unavailable"
    u = url or os.environ.get("REDIS_URL") or os.environ.get("VIEW_SYNC_REDIS_URL")
    if not u:
        try:
            host = os.environ.get("REDIS_HOST", "127.0.0.1")
            port = int(os.environ.get("REDIS_PORT", "6379"))
            r = redis.Redis(host=host, port=port, socket_connect_timeout=1.0, socket_timeout=1.0)
            r.ping()
            return "connected"
        except Exception:
            return "absent"
    try:
        r = redis.from_url(u, socket_connect_timeout=1.0, socket_timeout=1.0)
        r.ping()
        return "connected"
    except Exception:
        return "error"


def tle_freshness_fields(
    tle_cache: Dict[str, Any],
    tle_cache_file: str,
) -> tuple[Optional[int], str]:
    """
    Âge en secondes depuis last_refresh_iso du cache, sinon mtime du fichier.
    """
    src = "unknown"
    age: Optional[int] = None
    last_iso = tle_cache.get("last_refresh_iso") if isinstance(tle_cache, dict) else None
    if last_iso:
        age = _parse_iso_age_seconds(str(last_iso))
        src = str(tle_cache.get("source") or "cache_memory")
    if age is None and tle_cache_file:
        try:
            p = Path(tle_cache_file)
            if p.is_file():
                m = p.stat().st_mtime
                age = max(0, int(datetime.now(timezone.utc).timestamp() - m))
                src = "cache_local_file"
        except Exception:
            pass
    return age, src


def external_api_hint(tle_cache: Dict[str, Any]) -> str:
    if not isinstance(tle_cache, dict):
        return "unknown"
    err = tle_cache.get("error")
    if err:
        return "degraded"
    st = str(tle_cache.get("status") or "").lower()
    if st in ("error", "failed", "stale"):
        return "degraded"
    return "ok"


def build_operational_health(
    station_root: str,
    db_path: str,
    tle_cache: Dict[str, Any],
    tle_cache_file: str,
    *,
    ws_present: bool = True,
    sse_present: bool = True,
) -> Dict[str, Any]:
    """
    Charge utile JSON stable pour monitoring (tolérant : chaque sonde isolée).
    """
    out: Dict[str, Any] = {
        "status": "ok",
        "tle_age_seconds": None,
        "tle_source": "unknown",
        "redis": "unknown",
        "sqlite": "unknown",
        "external_api": "unknown",
        "ws_status": "present" if ws_present else "unknown",
        "sse_status": "present" if sse_present else "unknown",
        "timestamp": _utc_now_iso(),
    }
    try:
        age, tsrc = tle_freshness_fields(tle_cache, tle_cache_file)
        out["tle_age_seconds"] = age
        out["tle_source"] = tsrc
    except Exception:
        pass
    try:
        out["sqlite"] = probe_sqlite(db_path)
    except Exception:
        out["sqlite"] = "error"
    try:
        out["redis"] = probe_redis()
    except Exception:
        out["redis"] = "error"
    try:
        out["external_api"] = external_api_hint(tle_cache)
    except Exception:
        out["external_api"] = "unknown"
    # Dégradation globale si SQLite critique en erreur
    if out["sqlite"] == "error":
        out["status"] = "degraded"
    elif out["external_api"] == "degraded":
        out["status"] = "degraded"
    return out


def data_credibility_stub(
    tle_cache: Dict[str, Any],
    tle_cache_file: str,
) -> Dict[str, Any]:
    """
    Métadonnées honnêtes pour affichage / API (pas de « live » trompeur).
    """
    age, src = tle_freshness_fields(tle_cache, tle_cache_file)
    err = tle_cache.get("error") if isinstance(tle_cache, dict) else None
    level = "high"
    if err:
        level = "low"
    elif age is not None and age > 86400:
        level = "medium"
    elif age is not None and age > 3600:
        level = "medium"
    return {
        "source_label": src,
        "collection_time_iso": tle_cache.get("last_refresh_iso") if isinstance(tle_cache, dict) else None,
        "age_seconds": age,
        "confidence_level": level,
        "degraded": bool(err),
        "note": "cache_fallback" if src.startswith("cache") or "file" in src else "memory_or_remote",
    }
