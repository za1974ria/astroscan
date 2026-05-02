"""Cache centralisé AstroScan — Backend Redis (workers partagent le cache).

Migration vers Redis (CTO Phase 0 — Critique #2 : Cache/CB par worker).
Source unique extraite de station_web.py.

Architecture Redis :
  - _CACHE        -> prefix "as:cache:"     (API simple cache_get/cache_set)
  - _FEEDS_CACHE  -> prefix "as:feeds:"     (feeds externes get_cached)
  - ANALYTICS_CACHE -> prefix "as:analytics:" (analytics SQLite)

API publique inchangee -> station_web.py n'a aucune modification a faire.
"""

import json
import logging
import os
import time as _time

log = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

PREFIX_CACHE = "as:cache:"
PREFIX_FEEDS = "as:feeds:"
PREFIX_ANALYTICS = "as:analytics:"

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            _redis_client = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                decode_responses=False,
                socket_connect_timeout=2, socket_timeout=2,
            )
            _redis_client.ping()
            log.info("[Cache] Redis connected %s:%s db=%s", REDIS_HOST, REDIS_PORT, REDIS_DB)
        except Exception as e:
            log.error("[Cache] Redis unavailable: %s", e)
            _redis_client = False
    return _redis_client if _redis_client else None


def _safe_dumps(value):
    try:
        return json.dumps(value, default=str).encode("utf-8")
    except Exception:
        return json.dumps(str(value)).encode("utf-8")


def _safe_loads(value):
    if value is None:
        return None
    try:
        return json.loads(value.decode("utf-8") if isinstance(value, bytes) else value)
    except Exception:
        return None


class _AnalyticsCache:
    def get(self, key):
        c = _get_redis()
        if c is None:
            return None
        try:
            return _safe_loads(c.get(PREFIX_ANALYTICS + str(key)))
        except Exception as e:
            log.warning("[AnalyticsCache] GET failed: %s", e)
            return None

    def set(self, key, val, ttl=30):
        c = _get_redis()
        if c is None:
            return
        try:
            c.setex(PREFIX_ANALYTICS + str(key), ttl, _safe_dumps(val))
        except Exception as e:
            log.warning("[AnalyticsCache] SET failed: %s", e)

    def invalidate(self, key):
        c = _get_redis()
        if c is None:
            return
        try:
            c.delete(PREFIX_ANALYTICS + str(key))
        except Exception as e:
            log.warning("[AnalyticsCache] INVALIDATE failed: %s", e)

    def clear_expired(self):
        pass


ANALYTICS_CACHE = _AnalyticsCache()


def cache_get(key, ttl):
    c = _get_redis()
    if c is None:
        return None
    try:
        return _safe_loads(c.get(PREFIX_CACHE + str(key)))
    except Exception as e:
        log.warning("[Cache] GET failed: %s", e)
        return None


def cache_set(key, value, ttl=3600):
    c = _get_redis()
    if c is None:
        return
    try:
        c.setex(PREFIX_CACHE + str(key), ttl, _safe_dumps(value))
    except Exception as e:
        log.warning("[Cache] SET failed: %s", e)


def cache_cleanup():
    pass


def get_cached(key, ttl, fetch_fn):
    c = _get_redis()
    rkey = PREFIX_FEEDS + str(key)
    if c is not None:
        try:
            cached = c.get(rkey)
            if cached is not None:
                v = _safe_loads(cached)
                if v is not None:
                    return v
        except Exception as e:
            log.warning("[FeedsCache] GET failed: %s", e)
    try:
        data = fetch_fn()
    except Exception as e:
        log.warning("[FeedsCache] fetch_fn failed: %s", e)
        data = None
    if data is not None and c is not None:
        try:
            c.setex(rkey, ttl, _safe_dumps(data))
        except Exception as e:
            log.warning("[FeedsCache] SET failed: %s", e)
    return data


def invalidate_cache(key):
    c = _get_redis()
    if c is None:
        return
    try:
        skey = str(key)
        c.delete(PREFIX_CACHE + skey, PREFIX_FEEDS + skey, PREFIX_ANALYTICS + skey)
    except Exception as e:
        log.warning("[Cache] INVALIDATE failed: %s", e)


def invalidate_all():
    c = _get_redis()
    if c is None:
        return
    try:
        for prefix in (PREFIX_CACHE, PREFIX_FEEDS, PREFIX_ANALYTICS):
            cursor = 0
            while True:
                cursor, keys = c.scan(cursor=cursor, match=prefix + "*", count=100)
                if keys:
                    c.delete(*keys)
                if cursor == 0:
                    break
    except Exception as e:
        log.warning("[Cache] INVALIDATE_ALL failed: %s", e)


def cache_status():
    c = _get_redis()
    if c is None:
        return {"backend": "redis", "available": False, "api_cache": {"count": 0, "entries": []}, "feeds_cache": {"count": 0, "entries": []}}

    def _scan(prefix):
        out = []
        try:
            cursor = 0
            while True:
                cursor, keys = c.scan(cursor=cursor, match=prefix + "*", count=100)
                for k in keys:
                    ks = k.decode("utf-8") if isinstance(k, bytes) else k
                    try:
                        ttl = c.ttl(k)
                        out.append({"key": ks.replace(prefix, "", 1), "ttl_remaining_s": int(ttl) if ttl and ttl > 0 else 0})
                    except Exception:
                        continue
                if cursor == 0:
                    break
        except Exception as e:
            log.warning("[Cache] scan(%s) failed: %s", prefix, e)
        return out

    api_e = _scan(PREFIX_CACHE)
    feeds_e = _scan(PREFIX_FEEDS)
    return {
        "backend": "redis", "available": True,
        "host": REDIS_HOST, "port": REDIS_PORT, "db": REDIS_DB,
        "api_cache": {"count": len(api_e), "entries": api_e},
        "feeds_cache": {"count": len(feeds_e), "entries": feeds_e},
    }
