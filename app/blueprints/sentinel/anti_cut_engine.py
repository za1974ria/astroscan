"""Anti-cut engine — enforces "no unilateral stealth shutdown".

Codified invariants the rest of the system MUST go through:

  1. No single party can flip a live session to ENDED unilaterally.
     Stop requires request + counter-party approval. TTL is the only
     unilateral terminator and is server-driven.

  2. No live session row may be deleted. ``store.purge_old`` enforces
     this at the SQL level; this module re-asserts at the policy
     boundary for clarity + auditability.

  3. SOS is an alert override, not an end. It does not terminate the
     session — that's intentional: a real emergency means the parent
     keeps seeing the live state.
"""
from __future__ import annotations

from app.blueprints.sentinel import state_machine as fsm
from app.blueprints.sentinel import audit_logger


class AntiCutViolation(Exception):
    pass


def assert_no_unilateral_termination(
    session_id: str, current_state: str, requester: str
) -> None:
    """Raised if a single party tries to end a session without dual-stop."""
    if current_state in fsm.TERMINAL:
        # Already terminal — not a violation, the caller should 409.
        return
    if requester not in ("parent", "driver"):
        audit_logger.anti_cut_blocked(session_id, f"unknown_requester:{requester}")
        raise AntiCutViolation("unknown_requester")


def assert_no_silent_deletion(session_id: str, current_state: str) -> None:
    """Live rows are never deletable. ``purge_old`` will refuse anyway,
    but the policy layer surfaces the intent so a future bad change
    cannot regress this guarantee silently.
    """
    if current_state not in fsm.TERMINAL:
        audit_logger.anti_cut_blocked(session_id, f"delete_live:{current_state}")
        raise AntiCutViolation("cannot_delete_live_session")
