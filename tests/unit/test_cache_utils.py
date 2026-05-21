"""Unit tests — app.utils.cache.

Couvre MemoryCache, memoize_ttl, et les ré-exports Redis (mode no-op si
services.cache_service indisponible).
"""

from __future__ import annotations

import time

import pytest

from app.utils import cache as cache_mod

pytestmark = pytest.mark.unit


# ── MemoryCache ──────────────────────────────────────────────────────────────


def test_memory_cache_set_and_get():
    c = cache_mod.MemoryCache(ttl=10)
    c.set("k", "v")
    assert c.get("k") == "v"


def test_memory_cache_missing_key_returns_none():
    c = cache_mod.MemoryCache(ttl=10)
    assert c.get("nope") is None


def test_memory_cache_ttl_expiry():
    c = cache_mod.MemoryCache(ttl=0.05)
    c.set("k", "v")
    time.sleep(0.1)
    assert c.get("k") is None


def test_memory_cache_custom_ttl_per_set():
    c = cache_mod.MemoryCache(ttl=10)
    c.set("k", "v", ttl=0.05)
    time.sleep(0.1)
    assert c.get("k") is None


def test_memory_cache_delete():
    c = cache_mod.MemoryCache(ttl=10)
    c.set("k", "v")
    c.delete("k")
    assert c.get("k") is None


def test_memory_cache_clear():
    c = cache_mod.MemoryCache(ttl=10)
    c.set("a", 1)
    c.set("b", 2)
    c.clear()
    assert len(c) == 0


def test_memory_cache_len():
    c = cache_mod.MemoryCache(ttl=10)
    c.set("a", 1)
    c.set("b", 2)
    assert len(c) == 2


def test_memory_cache_status_shape():
    c = cache_mod.MemoryCache(ttl=10)
    c.set("a", 1)
    s = c.status()
    assert s["backend"] == "memory"
    assert s["count"] >= 1
    assert isinstance(s["entries"], list)


def test_memory_cache_eviction_at_max_size():
    c = cache_mod.MemoryCache(ttl=10, max_size=4)
    for i in range(8):
        c.set(f"k{i}", i)
    # After eviction the store size must not exceed max_size by much.
    assert len(c) <= 4


def test_memory_cache_overwrite():
    c = cache_mod.MemoryCache(ttl=10)
    c.set("k", "v1")
    c.set("k", "v2")
    assert c.get("k") == "v2"


# ── memoize_ttl ──────────────────────────────────────────────────────────────


def test_memoize_ttl_caches_results():
    calls = {"n": 0}

    @cache_mod.memoize_ttl(ttl=10)
    def f(x):
        calls["n"] += 1
        return x * 2

    assert f(3) == 6
    assert f(3) == 6
    assert calls["n"] == 1


def test_memoize_ttl_different_args_different_cache():
    calls = {"n": 0}

    @cache_mod.memoize_ttl(ttl=10)
    def f(x):
        calls["n"] += 1
        return x * 2

    f(1)
    f(2)
    f(1)
    assert calls["n"] == 2


def test_memoize_ttl_none_not_cached():
    calls = {"n": 0}

    @cache_mod.memoize_ttl(ttl=10)
    def f():
        calls["n"] += 1
        return None

    f()
    f()
    assert calls["n"] == 2


def test_memoize_ttl_expiry():
    calls = {"n": 0}

    @cache_mod.memoize_ttl(ttl=0.05)
    def f():
        calls["n"] += 1
        return "v"

    f()
    time.sleep(0.1)
    f()
    assert calls["n"] == 2


def test_memoize_ttl_cache_clear():
    calls = {"n": 0}

    @cache_mod.memoize_ttl(ttl=10)
    def f():
        calls["n"] += 1
        return "v"

    f()
    f.cache_clear()
    f()
    assert calls["n"] == 2


def test_memoize_ttl_cache_status_attached():
    @cache_mod.memoize_ttl(ttl=10)
    def f():
        return "v"

    f()
    s = f.cache_status()
    assert s["backend"] == "memory"


# ── memoize / cached_with_ttl aliases ───────────────────────────────────────


def test_memoize_alias():
    @cache_mod.memoize(ttl=10)
    def f(x):
        return x

    assert f(7) == 7


def test_cached_with_ttl_alias():
    @cache_mod.cached_with_ttl(seconds=10)
    def f(x):
        return x

    assert f(9) == 9


# ── set_cached / invalidate aliases ─────────────────────────────────────────


def test_set_cached_alias_invokable():
    cache_mod.set_cached("axe1-test-key", "value", ttl=5)


def test_invalidate_alias_invokable():
    cache_mod.invalidate("axe1-test-key")


# ── get_cached fallback path ────────────────────────────────────────────────


def test_get_cached_callable():
    """get_cached is the documented entry point — call it with a fetcher."""
    val = cache_mod.get_cached("axe1-test-key-getcached", ttl=5, fetch_fn=lambda: {"ok": True})
    assert val is None or val == {"ok": True}


def test_cache_status_returns_dict():
    s = cache_mod.cache_status()
    assert isinstance(s, dict)


def test_analytics_cache_exposed():
    ac = cache_mod.ANALYTICS_CACHE
    assert ac is not None
    assert hasattr(ac, "get")
    assert hasattr(ac, "set")
