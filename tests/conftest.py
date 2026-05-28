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

import builtins
import io
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import pytest

# Resolve project root dynamically: this file is at <PROJECT_ROOT>/tests/conftest.py
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _PROJECT_ROOT)

# Axe 1 — make station_web.py:284 (`for line in open(env_file)`) tolerate a
# .env that is unreadable (mode 0600 root-owned in production) OR absent
# (CI runners without secrets-as-file). The patch returns an empty StringIO
# for /root/astro_scan/.env so the loop iterates over zero lines and
# station_web continues its boot. Production runs as root with a real .env
# and is unaffected; only the test session sees this fallback.
# SECRET_KEY/SENTRY_DSN/TESTING are then posed by the fixtures below before
# importing the app, so the factory still gets a valid (test-only) secret.
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
if not hasattr(builtins, "_axe1_original_open"):
    builtins._axe1_original_open = builtins.open

    def _axe1_open(file, *args, **kwargs):
        try:
            return builtins._axe1_original_open(file, *args, **kwargs)
        except (PermissionError, FileNotFoundError):
            try:
                if os.path.abspath(str(file)) == os.path.abspath(_ENV_PATH):
                    return io.StringIO("")
            except Exception:
                pass
            raise

    builtins.open = _axe1_open


def _safe_rotating_handler(filename, *args, **kwargs):
    try:
        return logging.handlers._OriginalRotatingFileHandler(filename, *args, **kwargs)
    except (PermissionError, OSError):
        return logging.StreamHandler()


if not hasattr(logging.handlers, "_OriginalRotatingFileHandler"):
    logging.handlers._OriginalRotatingFileHandler = logging.handlers.RotatingFileHandler
    logging.handlers.RotatingFileHandler = _safe_rotating_handler


def _data_dir_writable() -> bool:
    """Return True if <PROJECT_ROOT>/data is writable by the current user.

    Importing station_web triggers _init_visits_table() which writes to
    data/visitors.db. In production data/ is owned by the service user and is
    writable; on locked-down dev/CI runners it may be read-only. We skip
    cleanly in that case rather than letting station_web crash mid-import.
    """
    data_dir = os.path.join(_PROJECT_ROOT, "data")
    return os.path.isdir(data_dir) and os.access(data_dir, os.W_OK)


@pytest.fixture(scope="session")
def app():
    """Legacy monolith app (station_web:app).

    Boots even when /root/astro_scan/.env is absent or unreadable: the
    builtin ``open`` patch above turns those errors into an empty StringIO,
    and the env vars below seed a test-only SECRET_KEY before import.
    """
    if not _data_dir_writable():
        pytest.skip(
            "app skipped — data/ is not writable by current user "
            "(station_web initializes visitors.db at import). "
            "Grant write to data/ to enable these tests."
        )

    os.environ["TESTING"] = "1"
    os.environ.setdefault("SENTRY_DSN", "")
    os.environ.setdefault("SECRET_KEY", "test-only-secret-key-min-32-chars-ok")
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

    Boots even when /root/astro_scan/.env is absent or unreadable: the open
    patch above + the env vars below provide a self-contained test config
    (SECRET_KEY ≥ 32 chars to satisfy MIN_SECRET_KEY_LEN_PRODUCTION should the
    config_name resolve to production; in 'testing' mode the factory is
    additionally lenient).
    """
    if not _data_dir_writable():
        pytest.skip(
            "factory_app skipped — data/ is not writable by current user "
            "(station_web initializes visitors.db at import, which the factory "
            "pre-loads for global state). Grant write to data/ to enable these tests."
        )

    os.environ["TESTING"] = "1"
    os.environ.setdefault("SENTRY_DSN", "")
    os.environ.setdefault("SECRET_KEY", "test-only-secret-key-min-32-chars-ok")
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
