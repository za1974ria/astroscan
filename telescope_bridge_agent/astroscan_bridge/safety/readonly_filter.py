"""Read-only enforcement — final safety net before any property read.

Concrete adapters MUST call `enforce_property_allowlist(kind, name)`
before issuing any ASCOM getattr / Alpaca GET. If a future maintainer
adds a property to the read flow that isn't on the per-kind allow-list,
this function raises and the read is aborted.

This module also exposes `assert_no_write_method(name)` for adapters
that want to defensively validate method names at runtime (even though
no adapter calls any method in V1).
"""
from __future__ import annotations

from astroscan_bridge.adapters.base import READ_PROPERTIES_BY_KIND


# Names of operations that MUST NEVER be invoked. Used by the optional
# `assert_no_write_method()` defensive check.
FORBIDDEN_OPERATION_TOKENS: frozenset[str] = frozenset({
    "slew", "park", "goto", "move", "pulse", "sync", "motor",
    # additional ASCOM action verbs that are not in the user's forbidden
    # list but are still write operations and must never be called.
    "abort", "unpark", "findhome", "halt", "shutdown", "stop",
})


class WriteAttemptError(PermissionError):
    """Raised whenever a write/actuate operation is attempted in V1."""


def enforce_property_allowlist(kind: str, property_name: str) -> None:
    """Raise WriteAttemptError if property_name isn't in the allow-list
    for the device kind. Property names are case-sensitive PascalCase
    matching the ASCOM specification."""
    allow = READ_PROPERTIES_BY_KIND.get(kind)
    if allow is None:
        raise WriteAttemptError(
            f"unknown device kind {kind!r} — refusing to read any property"
        )
    if property_name not in allow:
        raise WriteAttemptError(
            f"property {property_name!r} is not on the read-only allow-list "
            f"for kind={kind!r}. Refusing access."
        )


def assert_no_write_method(method_name: str) -> None:
    """Defensive check: raise if `method_name` looks like a write/actuate
    operation. Not called in the normal read flow, but available for
    adapters that introspect driver capabilities and want a hard guard."""
    low = method_name.lower()
    for tok in FORBIDDEN_OPERATION_TOKENS:
        if tok in low:
            raise WriteAttemptError(
                f"method {method_name!r} contains forbidden token {tok!r}; "
                f"V1 is read-only."
            )
