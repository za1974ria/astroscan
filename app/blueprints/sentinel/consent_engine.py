"""Consent engine — enforces the legal/ethical contract.

Hard invariants:
  - No location data may be collected before the driver explicitly
    consents (the ``mark_accepted`` server-side gate).
  - The ``ACTIVE`` state is the only proof-of-consent the rest of the
    system trusts. ``driver_consent_at`` is written at that transition
    and never modified.

This module never touches the database directly; it returns a typed
result that ``session_manager`` translates into a state change.
"""
from __future__ import annotations

from app.blueprints.sentinel import state_machine as fsm
from app.blueprints.sentinel import store, audit_logger


class ConsentResult:
    __slots__ = ("ok", "reason")

    def __init__(self, ok: bool, reason: str | None = None):
        self.ok = ok
        self.reason = reason


def attempt_accept(session_id: str) -> ConsentResult:
    """Driver-initiated transition PENDING_DRIVER → ACTIVE."""
    row = store.get_session(session_id)
    if row is None:
        return ConsentResult(False, "session_not_found")
    if row["state"] == fsm.ACTIVE:
        return ConsentResult(False, "already_active")
    if row["state"] != fsm.PENDING_DRIVER:
        audit_logger.consent_blocked(session_id, f"state_{row['state'].lower()}")
        return ConsentResult(False, f"cannot_accept_in_state_{row['state'].lower()}")
    if not store.mark_accepted(session_id):
        return ConsentResult(False, "accept_failed")
    audit_logger.driver_accepted(session_id)
    return ConsentResult(True)


def assert_consent_for_update(state: str) -> bool:
    """Position updates only allowed while ACTIVE/STOP_PENDING_*."""
    return state in fsm.LIVE
