"""Smoke tests — WSGI loader (PASS 18 bascule strategy).

The ``wsgi.py`` entry point implements a 3-tier loader:

1. ``ASTROSCAN_FORCE_MONOLITH=1`` → explicit fallback to legacy ``station_web``.
2. ``import station_web`` (init globals) → ``app.create_app('production')``.
3. except → fallback to legacy ``station_web``.

These tests validate the import-time behaviour without restarting Gunicorn.
They require the test runner to be able to read ``/root/astro_scan/.env``
(production runs as root; if you run the suite as a non-root user without
read access, the entire module is skipped).
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest
from flask import Flask


from pathlib import Path as _Path
_ENV_PATH = str(_Path(__file__).resolve().parent.parent.parent / ".env")
# PASS 2D fix (2026-05-07) — skip if .env is missing OR not readable.
# Previously only checked "exists AND not readable", which let CI pass
# the gate (no .env) and then fail on factory load (env_guard rejects
# fake SECRET_KEY). Aligned with tests/conftest.py logic.
if not os.path.exists(_ENV_PATH) or not os.access(_ENV_PATH, os.R_OK):
    pytest.skip(
        f"WSGI smoke tests skipped — {_ENV_PATH} is missing or not "
        "readable by the current user. Run as root with .env present "
        "(production runs as root) to enable these tests.",
        allow_module_level=True,
    )

pytestmark = pytest.mark.smoke


def _reload_wsgi():
    """Force-reload wsgi to re-evaluate the loader."""
    sys.modules.pop("wsgi", None)
    return importlib.import_module("wsgi")


def test_wsgi_module_imports():
    wsgi = _reload_wsgi()
    assert wsgi is not None


def test_wsgi_app_object_is_flask():
    wsgi = _reload_wsgi()
    assert isinstance(wsgi.app, Flask)


def test_wsgi_app_serves_routes():
    wsgi = _reload_wsgi()
    n = sum(1 for _ in wsgi.app.url_map.iter_rules())
    assert n >= 200, f"WSGI app exposes only {n} routes (expected ≥ 200)"


def test_wsgi_force_monolith_env_var(monkeypatch):
    """Setting ASTROSCAN_FORCE_MONOLITH must short-circuit to the monolith."""
    monkeypatch.setenv("ASTROSCAN_FORCE_MONOLITH", "1")
    wsgi = _reload_wsgi()
    assert isinstance(wsgi.app, Flask)
    # The monolith path is the same Flask object as station_web.app
    import station_web
    assert wsgi.app is station_web.app
    monkeypatch.delenv("ASTROSCAN_FORCE_MONOLITH", raising=False)


def test_wsgi_force_monolith_accepts_truthy_values(monkeypatch):
    for truthy in ("1", "true", "yes", "on"):
        monkeypatch.setenv("ASTROSCAN_FORCE_MONOLITH", truthy)
        wsgi = _reload_wsgi()
        import station_web
        assert wsgi.app is station_web.app, (
            f"ASTROSCAN_FORCE_MONOLITH={truthy!r} did not trigger fallback"
        )
    monkeypatch.delenv("ASTROSCAN_FORCE_MONOLITH", raising=False)
