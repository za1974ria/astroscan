"""Unit tests — services.cache_service (Redis-backed cache layers).

Uses a FakeRedis stub so tests run without a live Redis. Exercises all 3
prefixes (api / feeds / analytics) plus the fallback when Redis is down.
"""

from __future__ import annotations

import json

import pytest

from services import cache_service as cs

pytestmark = pytest.mark.unit


class FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v):
        self.store[k] = v if isinstance(v, bytes) else str(v).encode()

    def setex(self, k, ttl, v):
        self.store[k] = v if isinstance(v, bytes) else str(v).encode()
        self.ttls[k] = ttl

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
            self.ttls.pop(k, None)

    def ttl(self, k):
        return self.ttls.get(k, -1)

    def scan(self, cursor=0, match=None, count=100):
        prefix = match.rstrip("*") if match else ""
        keys = [k for k in self.store.keys() if k.startswith(prefix)]
        return (0, keys)

    def ping(self):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(cs, "_redis_client", None)
    monkeypatch.setattr(cs, "_get_redis", lambda: fr)
    return fr


@pytest.fixture
def no_redis(monkeypatch):
    monkeypatch.setattr(cs, "_redis_client", None)
    monkeypatch.setattr(cs, "_get_redis", lambda: None)


# ── _safe_dumps / _safe_loads ────────────────────────────────────────────────


def test_safe_dumps_dict():
    blob = cs._safe_dumps({"a": 1})
    assert json.loads(blob) == {"a": 1}


def test_safe_dumps_list():
    blob = cs._safe_dumps([1, 2, 3])
    assert json.loads(blob) == [1, 2, 3]


def test_safe_loads_bytes():
    assert cs._safe_loads(b'{"x": 5}') == {"x": 5}


def test_safe_loads_string():
    assert cs._safe_loads('{"x": 5}') == {"x": 5}


def test_safe_loads_none():
    assert cs._safe_loads(None) is None


def test_safe_loads_invalid_returns_none():
    assert cs._safe_loads(b"not json") is None


# ── cache_get / cache_set ────────────────────────────────────────────────────


def test_cache_set_then_get(fake_redis):
    cs.cache_set("k1", {"v": 1}, ttl=60)
    assert cs.cache_get("k1", ttl=60) == {"v": 1}


def test_cache_get_missing_returns_none(fake_redis):
    assert cs.cache_get("nope", ttl=60) is None


def test_cache_set_without_redis_silent(no_redis):
    cs.cache_set("k", "v")
    assert cs.cache_get("k", ttl=60) is None


def test_invalidate_cache_removes_all_prefixes(fake_redis):
    cs.cache_set("kx", "v1")
    cs.invalidate_cache("kx")
    assert cs.cache_get("kx", ttl=60) is None


def test_invalidate_cache_no_redis_silent(no_redis):
    cs.invalidate_cache("any")


# ── get_cached (feeds, with fetch fallback) ─────────────────────────────────


def test_get_cached_fetches_and_caches(fake_redis):
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"feed": "data"}

    v1 = cs.get_cached("feed1", ttl=60, fetch_fn=fetch)
    v2 = cs.get_cached("feed1", ttl=60, fetch_fn=fetch)
    assert v1 == v2 == {"feed": "data"}
    assert calls["n"] == 1


def test_get_cached_fetch_failure_returns_none(fake_redis):
    def fetch():
        raise RuntimeError("boom")

    assert cs.get_cached("bad", ttl=60, fetch_fn=fetch) is None


def test_get_cached_no_redis_still_runs_fetch(no_redis):
    assert cs.get_cached("k", ttl=60, fetch_fn=lambda: 42) == 42


# ── ANALYTICS_CACHE ──────────────────────────────────────────────────────────


def test_analytics_cache_set_get(fake_redis):
    cs.ANALYTICS_CACHE.set("ak", [1, 2, 3], ttl=15)
    assert cs.ANALYTICS_CACHE.get("ak") == [1, 2, 3]


def test_analytics_cache_get_missing(fake_redis):
    assert cs.ANALYTICS_CACHE.get("missing") is None


def test_analytics_cache_invalidate(fake_redis):
    cs.ANALYTICS_CACHE.set("ak", "v")
    cs.ANALYTICS_CACHE.invalidate("ak")
    assert cs.ANALYTICS_CACHE.get("ak") is None


def test_analytics_cache_no_redis_silent(no_redis):
    cs.ANALYTICS_CACHE.set("ak", "v")
    cs.ANALYTICS_CACHE.invalidate("ak")
    assert cs.ANALYTICS_CACHE.get("ak") is None


def test_analytics_cache_clear_expired_is_noop():
    cs.ANALYTICS_CACHE.clear_expired()  # must not raise


# ── invalidate_all ───────────────────────────────────────────────────────────


def test_invalidate_all(fake_redis):
    cs.cache_set("a", 1)
    cs.cache_set("b", 2)
    cs.invalidate_all()
    assert cs.cache_get("a", ttl=60) is None
    assert cs.cache_get("b", ttl=60) is None


def test_invalidate_all_no_redis_silent(no_redis):
    cs.invalidate_all()


# ── cache_status ─────────────────────────────────────────────────────────────


def test_cache_status_available(fake_redis):
    cs.cache_set("a", 1)
    s = cs.cache_status()
    assert s["backend"] == "redis"
    assert s["available"] is True
    assert "api_cache" in s
    assert "feeds_cache" in s


def test_cache_status_unavailable(no_redis):
    s = cs.cache_status()
    assert s["available"] is False


# ── cache_cleanup is a no-op ─────────────────────────────────────────────────


def test_cache_cleanup_does_not_raise():
    cs.cache_cleanup()
