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

# Axe 1 (2026-05-29) — if the repo's data/ is not writable by the current user
# (typical on the Hetzner box where data/ is root:root 755 but the runner is
# zakaria), bootstrap a writable shadow root under /tmp and redirect STATION
# there. Code/templates are symlinked back to the real repo so behavior is
# identical; only data/ + logs/ live in tmp. The shadow is built ahead of any
# import of station_web / app so paths.py picks up ASTROSCAN_HOME on first read.
_DATA_DIR_REPO = os.path.join(_PROJECT_ROOT, "data")
if not os.access(_DATA_DIR_REPO, os.W_OK):
    _SHADOW_ROOT = "/tmp/astroscan_test_root"
    _SHADOW_DATA = os.path.join(_SHADOW_ROOT, "data")
    if os.path.isdir(_SHADOW_DATA) and os.access(_SHADOW_DATA, os.W_OK):
        os.environ.setdefault("ASTROSCAN_HOME", _SHADOW_ROOT)
        os.environ.setdefault("STATION", _SHADOW_ROOT)
        os.environ.setdefault("ASTROSCAN_DATA_DIR", _SHADOW_DATA)
        os.environ.setdefault("ASTROSCAN_LOG_DIR", os.path.join(_SHADOW_ROOT, "logs"))
        # Make subsequent imports resolve files from the shadow root first;
        # symlinks point back to the real repo so identity is preserved.
        sys.path.insert(0, _SHADOW_ROOT)

# Axe 1 — make station_web.py:284 (`for line in open(env_file)`) tolerate a
# .env that is unreadable (mode 0600 root-owned in production) OR absent
# (CI runners without secrets-as-file). The patch returns an empty StringIO
# for /root/astro_scan/.env so the loop iterates over zero lines and
# station_web continues its boot. Production runs as root with a real .env
# and is unaffected; only the test session sees this fallback.
# SECRET_KEY/SENTRY_DSN/TESTING are then posed by the fixtures below before
# importing the app, so the factory still gets a valid (test-only) secret.
_ENV_PATHS = {os.path.realpath(os.path.join(_PROJECT_ROOT, ".env"))}
_shadow_root_env = os.environ.get("ASTROSCAN_HOME")
if _shadow_root_env:
    _ENV_PATHS.add(os.path.realpath(os.path.join(_shadow_root_env, ".env")))
if not hasattr(builtins, "_axe1_original_open"):
    builtins._axe1_original_open = builtins.open

    def _axe1_open(file, *args, **kwargs):
        try:
            return builtins._axe1_original_open(file, *args, **kwargs)
        except (PermissionError, FileNotFoundError):
            try:
                # Match by realpath so symlinks from a shadow root resolve back
                # to the real .env, and abspath fallback covers the un-resolved
                # original argument passed by callers like station_web.
                fpath = str(file)
                if os.path.realpath(fpath) in _ENV_PATHS or os.path.abspath(fpath) in _ENV_PATHS:
                    return io.StringIO("")
                if os.path.basename(fpath) == ".env":
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
    """Return True if a usable, writable data dir is available.

    Importing station_web triggers _init_visits_table() which writes to
    data/visitors.db. We accept either the repo-local data/ or, when that
    is not writable (e.g. data/ root-owned on the production host while
    tests run as zakaria), the shadow data dir under ASTROSCAN_DATA_DIR
    bootstrapped at conftest load time.
    """
    candidates = [os.path.join(_PROJECT_ROOT, "data")]
    env_data = os.environ.get("ASTROSCAN_DATA_DIR")
    if env_data:
        candidates.insert(0, env_data)
    return any(os.path.isdir(d) and os.access(d, os.W_OK) for d in candidates)


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
