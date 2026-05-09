"""
app.utils.cache — Façade cache centralisée pour les Blueprints AstroScan.

Deux niveaux de cache :
  1. Redis (partagé entre workers) via services.cache_service
     → get_cached, cache_get, cache_set, invalidate_cache, invalidate_all,
       cache_status, ANALYTICS_CACHE
  2. Mémoire in-process (MemoryCache) pour les cas simples à TTL court
     → Remplace les dicts globaux _chat_cache, _flights_cache, _CAM_IMG_CACHE…

Usage dans les Blueprints :
    from app.utils.cache import get_cached, MemoryCache

    _flights = MemoryCache(ttl=30)

    def get_flights():
        cached = _flights.get("data")
        if cached is not None:
            return cached
        data = _fetch()
        _flights.set("data", data)
        return data
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Re-export Redis-backed helpers depuis services.cache_service
# Les Blueprints importent depuis app.utils.cache, pas directement services.
# ---------------------------------------------------------------------------
try:
    from services.cache_service import (  # noqa: F401
        ANALYTICS_CACHE,
        cache_cleanup,
        cache_get,
        cache_set,
        cache_status,
        get_cached,
        invalidate_all,
        invalidate_cache,
    )
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    log.warning("[cache] services.cache_service introuvable — fallback no-op")

    def get_cached(key: str, ttl: int, fetch_fn: Callable) -> Any:  # type: ignore[misc]
        try:
            return fetch_fn()
        except Exception as exc:
            log.warning("[cache] get_cached fallback fetch failed: %s", exc)
            return None

    def cache_get(key: str, ttl: int) -> None:  # type: ignore[misc]
        return None

    def cache_set(key: str, value: Any, ttl: int = 3600) -> None:  # type: ignore[misc]
        pass

    def cache_cleanup() -> None:  # type: ignore[misc]
        pass

    def cache_status() -> dict:  # type: ignore[misc]
        return {"backend": "none", "available": False}

    def invalidate_cache(key: str) -> None:  # type: ignore[misc]
        pass

    def invalidate_all() -> None:  # type: ignore[misc]
        pass

    class _NoopAnalyticsCache:
        def get(self, key: str) -> None:
            return None
        def set(self, key: str, val: Any, ttl: int = 30) -> None:
            pass
        def invalidate(self, key: str) -> None:
            pass

    ANALYTICS_CACHE = _NoopAnalyticsCache()  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# MemoryCache — cache in-process à TTL, thread-safe
# Remplace les dicts globaux ad-hoc de station_web.py.
# ---------------------------------------------------------------------------

class MemoryCache:
    """Cache in-process thread-safe avec TTL par entrée.

    Exemple :
        _cam_cache = MemoryCache(ttl=30)
        data = _cam_cache.get("paris")
        if data is None:
            data = fetch_cam("paris")
            _cam_cache.set("paris", data)
    """

    def __init__(self, ttl: float = 300, max_size: int = 512) -> None:
        self._ttl = ttl
        self._max = max_size
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, val = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        effective_ttl = ttl if ttl is not None else self._ttl
        with self._lock:
            if len(self._store) >= self._max and key not in self._store:
                self._evict()
            self._store[key] = (time.monotonic(), value)
            if ttl is not None:
                # Stocker le TTL custom dans le timestamp futur
                self._store[key] = (time.monotonic() - self._ttl + effective_ttl, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict(self) -> None:
        """Supprime les entrées expirées, ou la moitié la plus ancienne."""
        now = time.monotonic()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]
        if len(self._store) >= self._max:
            sorted_keys = sorted(self._store, key=lambda k: self._store[k][0])
            for k in sorted_keys[: len(sorted_keys) // 2]:
                del self._store[k]

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def status(self) -> dict:
        with self._lock:
            now = time.monotonic()
            live = [(k, round(self._ttl - (now - ts), 1)) for k, (ts, _) in self._store.items()
                    if now - ts <= self._ttl]
        return {"backend": "memory", "count": len(live), "entries": [
            {"key": k, "ttl_remaining_s": ttl} for k, ttl in live
        ]}


# ---------------------------------------------------------------------------
# Décorateur @memoize_ttl pour fonctions pures (no-arg ou avec args hashables)
# ---------------------------------------------------------------------------

def memoize_ttl(ttl: float = 300, max_size: int = 256) -> Callable:
    """Décorateur mémoire TTL pour fonctions à arguments hashables.

    Exemple :
        @memoize_ttl(ttl=60)
        def get_tle_data(sat_name: str) -> dict: ...
    """
    _cache: MemoryCache = MemoryCache(ttl=ttl, max_size=max_size)

    def decorator(fn: Callable) -> Callable:
        import functools

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = str(args) + str(sorted(kwargs.items()))
            cached = _cache.get(key)
            if cached is not None:
                return cached
            result = fn(*args, **kwargs)
            if result is not None:
                _cache.set(key, result)
            return result

        wrapper.cache_clear = _cache.clear  # type: ignore[attr-defined]
        wrapper.cache_status = _cache.status  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Aliases pour compatibilité avec le nouveau spec Blueprint
# ---------------------------------------------------------------------------

def set_cached(key: str, value: Any, ttl: int = 300) -> None:
    """Alias de cache_set avec signature (key, value, ttl)."""
    cache_set(key, value, ttl)


def invalidate(key: str) -> None:
    """Alias de invalidate_cache."""
    invalidate_cache(key)


def memoize(ttl: float = 300, max_size: int = 256) -> Callable:
    """Alias de memoize_ttl — décorateur @memoize(ttl=N)."""
    return memoize_ttl(ttl=ttl, max_size=max_size)


def cached_with_ttl(seconds: float = 300, max_size: int = 256) -> Callable:
    """Alias de memoize_ttl — décorateur @cached_with_ttl(seconds=N)."""
    return memoize_ttl(ttl=seconds, max_size=max_size)
