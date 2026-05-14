"""Pure state machine for a protected trip session.

Lifecycle is one column. SOS is orthogonal (separate boolean).

  PENDING_DRIVER  → ACTIVE
  ACTIVE          → STOP_PENDING_PARENT | STOP_PENDING_DRIVER
  STOP_PENDING_*  → ENDED  (only by counter-party approval)
  Any non-terminal → EXPIRED (TTL, unilateral, by server only)
"""
from __future__ import annotations

PENDING_DRIVER = "PENDING_DRIVER"
ACTIVE = "ACTIVE"
STOP_PENDING_PARENT = "STOP_PENDING_PARENT"
STOP_PENDING_DRIVER = "STOP_PENDING_DRIVER"
ENDED = "ENDED"
EXPIRED = "EXPIRED"

LIVE = (ACTIVE, STOP_PENDING_PARENT, STOP_PENDING_DRIVER)
TERMINAL = (ENDED, EXPIRED)


def can_driver_update(state: str) -> bool:
    return state in LIVE


def can_request_stop(state: str, requester: str) -> bool:
    return state == ACTIVE and requester in ("parent", "driver")


def state_after_request(requester: str) -> str:
    return STOP_PENDING_PARENT if requester == "parent" else STOP_PENDING_DRIVER


def approver_for(state: str) -> str | None:
    if state == STOP_PENDING_PARENT:
        return "driver"
    if state == STOP_PENDING_DRIVER:
        return "parent"
    return None
