"""Service security — rate-limiting + extraction IP cliente.

PASS 2D Cat 5 (2026-05-07) : extraction depuis station_web.py de
  - `_api_rate_limit_allow` (fenêtre glissante anti-abus, thread-safe)
  - `_client_ip_from_request` (X-Forwarded-For / remote_addr)
  - Globals `_API_RATE_LOCK`, `_API_RATE_HITS` (état interne)

station_web.py conserve un re-export pour la compat des imports legacy.
"""
import threading
import time


_API_RATE_LOCK = threading.Lock()
_API_RATE_HITS: dict[str, list[float]] = {}


def _api_rate_limit_allow(key: str, limit: int, window_sec: int) -> tuple[bool, int]:
    """
    Fenêtre glissante simple anti-abus.
    Retourne (allowed, retry_after_sec).
    """
    now = time.time()
    try:
        with _API_RATE_LOCK:
            hits = _API_RATE_HITS.get(key, [])
            cutoff = now - float(window_sec)
            hits = [t for t in hits if t >= cutoff]
            if len(hits) >= int(limit):
                retry_after = max(1, int(window_sec - (now - hits[0])))
                _API_RATE_HITS[key] = hits
                return False, retry_after
            hits.append(now)
            _API_RATE_HITS[key] = hits
            # Garde-fou mémoire (rare)
            if len(_API_RATE_HITS) > 8000:
                for k in list(_API_RATE_HITS.keys())[:1500]:
                    arr = _API_RATE_HITS.get(k) or []
                    if not arr or arr[-1] < now - 3600:
                        _API_RATE_HITS.pop(k, None)
            return True, 0
    except Exception:
        return True, 0


def _client_ip_from_request(req):
    """Extrait l'IP client (X-Forwarded-For en priorité, sinon remote_addr)."""
    ip = req.headers.get("X-Forwarded-For", req.remote_addr or "")
    ip = (ip or "").split(",")[0].strip()
    return ip
