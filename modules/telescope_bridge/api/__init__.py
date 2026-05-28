"""TB-2 — Re-export the Flask blueprint for app/__init__.py consumption."""
from modules.telescope_bridge.api.routes import bp  # noqa: F401

__all__ = ["bp"]
