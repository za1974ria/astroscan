"""AstroScan Control Tower — observability core.

V1 package. Currently exposes ONLY the declarative registry loader.
Adapters, aggregator, state engine and Flask blueprint arrive in
subsequent patches. Nothing in this package is wired into the running
application yet (no Flask import, no side effects).
"""
from app.services.control_tower.registry import (  # noqa: F401
    Target,
    Registry,
    RegistryError,
    load_registry,
)

__all__ = ["Target", "Registry", "RegistryError", "load_registry"]
