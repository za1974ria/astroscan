"""Guardian blueprint — read-only monitoring agent (Session 1).

Exposes ``bp`` for registration with url_prefix='/api/guardian'.
Endpoints are localhost-only via @require_localhost.

The monitoring thread is started lazily on the first import of routes.py
(via agent.start_agent()) — start is idempotent.
"""
from app.blueprints.guardian.routes import bp

__all__ = ["bp"]
