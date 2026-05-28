"""AstroScan Control Tower — Remediation policies (Phase 4A, DRY-RUN).

Pure declarative module. NO behavior. NO imports beyond stdlib annotations.
Lists the match-action rules consumed by remediator.compute_suggestions().

A policy fires when:
  - the snapshot contains a service whose internal `id` equals policy['target_id']
  - that service's classified `state` is in policy['states']
  - the per-(policy, target) cooldown is not active

Every emitted suggestion is informational only. Operators must apply the
action manually. The remediator never executes anything.

Schema of a policy entry:
  policy_id        : stable unique identifier
  target_id        : id field of the target in targets.TARGETS
  states           : tuple of raw_state values that trigger the policy
                     (subset of {"red", "orange"})
  suggested_action : short imperative the operator can act upon
  risk_level       : "low" | "medium" | "high"
  reason_tpl       : str template; supports {detail} and {name} keys.
"""
from __future__ import annotations


# Default cooldown applied to every suggestion (seconds).
# 600 s = 10 min. Prevents the same suggestion from re-emitting on the
# next 10 s snapshot tick while the operator is acting on it.
COOLDOWN_SECONDS: int = 600


POLICIES: list[dict] = [
    {
        "policy_id": "p_gunicorn_restart",
        "target_id": "proc_gunicorn",
        "states": ("red",),
        "suggested_action": "restart astroscan.service",
        "risk_level": "high",
        "reason_tpl": "AstroScan gunicorn process not detected — {detail}",
        "allow_execution": True,   # PHASE 4C.1 — whitelisted in executor
    },
    {
        "policy_id": "p_nginx_restart",
        "target_id": "proc_nginx",
        "states": ("red",),
        "suggested_action": "restart nginx",
        "risk_level": "high",
        "reason_tpl": "Nginx process not detected — {detail}",
        "allow_execution": True,   # PHASE 4C.1 — whitelisted in executor
    },
    {
        "policy_id": "p_dns_check_provider",
        "target_id": "edge_dns",
        "states": ("red",),
        "suggested_action": "check DNS/provider",
        "risk_level": "medium",
        "reason_tpl": "DNS resolution failing — {detail}",
    },
    {
        "policy_id": "p_tls_renew",
        "target_id": "edge_tls",
        "states": ("orange", "red"),
        "suggested_action": "renew certificate",
        "risk_level": "medium",
        "reason_tpl": "TLS certificate condition — {detail}",
    },
    {
        "policy_id": "p_disk_root_free",
        "target_id": "sys_disk_root",
        "states": ("orange", "red"),
        "suggested_action": "free disk space",
        "risk_level": "medium",
        "reason_tpl": "Disk root pressure — {detail}",
    },
    {
        "policy_id": "p_ram_inspect",
        "target_id": "sys_ram",
        "states": ("orange", "red"),
        "suggested_action": "inspect memory pressure",
        "risk_level": "medium",
        "reason_tpl": "RAM pressure — {detail}",
    },
    {
        "policy_id": "p_cpu_inspect",
        "target_id": "sys_cpu",
        "states": ("orange", "red"),
        "suggested_action": "inspect CPU pressure",
        "risk_level": "low",
        "reason_tpl": "CPU pressure — {detail}",
    },
    {
        "policy_id": "p_tle_refresh",
        "target_id": "fresh_tle",
        "states": ("red",),
        "suggested_action": "refresh TLE collector",
        "risk_level": "low",
        "reason_tpl": "TLE payload sanity failing — {detail}",
    },
    {
        "policy_id": "p_iss_refresh",
        "target_id": "fresh_iss",
        "states": ("red",),
        "suggested_action": "refresh ISS source",
        "risk_level": "low",
        "reason_tpl": "ISS payload sanity failing — {detail}",
    },
    {
        "policy_id": "p_astrobrain_check",
        "target_id": "worker_astrobrain",
        "states": ("red",),
        "suggested_action": "check AstroBrain health endpoint",
        "risk_level": "low",
        "reason_tpl": "AstroBrain unavailable — {detail}",
    },
]

# Hard invariants — fail loud at import time if a policy is malformed.
_ALLOWED_RISK = {"low", "medium", "high"}
_ALLOWED_STATES = {"red", "orange"}
_seen_ids: set[str] = set()
for _p in POLICIES:
    assert _p["policy_id"] not in _seen_ids, f"duplicate policy_id {_p['policy_id']}"
    _seen_ids.add(_p["policy_id"])
    assert _p["risk_level"] in _ALLOWED_RISK, f"bad risk_level on {_p['policy_id']}"
    assert set(_p["states"]) <= _ALLOWED_STATES, f"bad states on {_p['policy_id']}"
    assert isinstance(_p["target_id"], str) and _p["target_id"], _p
    assert isinstance(_p["suggested_action"], str) and _p["suggested_action"], _p
    assert isinstance(_p["reason_tpl"], str) and _p["reason_tpl"], _p
del _seen_ids, _p
