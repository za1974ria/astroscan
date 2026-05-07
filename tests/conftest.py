"""Pytest fixtures for ASTRO-SCAN.

Two app fixtures are exposed:

- ``app`` — legacy Flask app loaded via ``station_web:app``. Kept for the
  pre-PASS-18 smoke tests that depend on globals initialized in the monolith.
- ``factory_app`` — clean Flask app from ``app.create_app("testing")``. Use
  this in new tests targeting the factory + blueprint architecture.

The session pre-patches ``logging.handlers.RotatingFileHandler`` so that
``station_web`` import does not crash when the production log directory
is not writable by the current user (typical for unprivileged CI runners).

PASS 2D (2026-05-07) — Project root is now resolved dynamically from
``__file__`` so that the suite works in any environment (Hetzner, GitHub
Actions, local dev, Docker), not only ``/root/astro_scan``.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

import pytest

# Resolve project root dynamically: this file is at <PROJECT_ROOT>/tests/conftest.py
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _PROJECT_ROOT)


def _safe_rotating_handler(filename, *args, **kwargs):
    try:
        return logging.handlers._OriginalRotatingFileHandler(filename, *args, **kwargs)
    except (PermissionError, OSError):
        return logging.StreamHandler()


if not hasattr(logging.handlers, "_OriginalRotatingFileHandler"):
    logging.handlers._OriginalRotatingFileHandler = logging.handlers.RotatingFileHandler
    logging.handlers.RotatingFileHandler = _safe_rotating_handler


@pytest.fixture(scope="session")
def app():
    """Legacy monolith app (station_web:app)."""
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    # Skip cleanly if .env is missing (CI) or not readable (unprivileged user)
    if not os.path.exists(env_path) or not os.access(env_path, os.R_OK):
        pytest.skip(
            f"app skipped — {env_path} is missing or not readable by the current user."
        )

    os.environ["TESTING"] = "1"
    os.environ.setdefault("SENTRY_DSN", "")
    os.environ.setdefault("SECRET_KEY", "test-only-secret-key")
    try:
        from station_web import app as flask_app
    except (PermissionError, OSError) as exc:
        pytest.skip(f"station_web could not load: {exc}")

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    yield flask_app


@pytest.fixture(scope="session")
def client(app):
    """Test client bound to the legacy monolith app."""
    return app.test_client()


@pytest.fixture(scope="session")
def factory_app():
    """Clean Flask app via ``app.create_app('testing')`` — post-PASS-18 target.

    The factory reads ``<PROJECT_ROOT>/.env`` at boot (mode 0600, root-owned in
    production). When the test runner does not have read access, the fixture
    skips cleanly rather than erroring — production runs as root and is
    unaffected.
    """
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.exists(env_path) or not os.access(env_path, os.R_OK):
        pytest.skip(
            f"factory_app skipped — {env_path} is missing or not readable by "
            "the current user (production runs as root). Run the suite as root "
            "or grant read access to the test runner to enable factory tests."
        )

    os.environ["TESTING"] = "1"
    os.environ.setdefault("SENTRY_DSN", "")
    os.environ.setdefault("SECRET_KEY", "test-only-secret-key")
    # Pre-load station_web so global state (TLE cache, threads) is up before
    # the factory imports the blueprints that lazy-import from it.
    try:
        import station_web  # noqa: F401  — side effects required

        from app import create_app

        flask_app = create_app("testing")
    except (PermissionError, OSError) as exc:
        pytest.skip(f"factory_app could not load: {exc}")

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture(scope="session")
def factory_client(factory_app):
    """Test client bound to the factory app."""
    return factory_app.test_client()
