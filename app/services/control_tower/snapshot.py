"""AstroScan Control Tower — Snapshot builder (Phase 3A).

Builds the JSON consumed by /api/control-tower/snapshot. Shape is kept
backward-compatible with the existing maintenance.html dashboard:

  {
    "timestamp": "...", "uptime": "LIVE",
    "global": {"status": "ok|warn|down",
               "ok_count": n, "warn_count": n, "down_count": n,
               "total": 53},
    "alerts": [...],
    "categories": {
        "infrastructure": [...],
        "external_apis":  [...],
        "data_quality":   [...],
        "workers":        [...]
    }
  }

Each card item adds two NEW fields (additive, non-breaking):
  category   : semantic category (edge|core_api|module_page|system|
               data|freshness|worker)
  raw_state  : "green"|"orange"|"red"|"grey"

53 probes are executed in parallel via ThreadPoolExecutor (stdlib).
Each probe enforces its own timeout; the executor itself does not block
on slow probes (each Future already has a bounded run).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.services.control_tower.targets import TARGETS
from app.services.control_tower.probes import run_probe
from app.services.control_tower.classifiers import classify
from app.services.control_tower.remediator import compute_suggestions


# ── Legacy 4-bucket projection ───────────────────────────────────────
_BUCKETS = {
    "edge":        "infrastructure",
    "system":      "infrastructure",
    "module_page": "infrastructure",
    "core_api":    "external_apis",
    "data":        "data_quality",
    "freshness":   "data_quality",
    "worker":      "workers",
}


def _bucket_for(category: str) -> str:
    return _BUCKETS.get(category, "infrastructure")


def _legacy_status(state: str) -> str:
    """Map 4-state model onto the 3-state model the legacy frontend uses.

    grey is mapped to 'warn' (not 'down'): an un-measured optional probe
    must never look like a hard failure on the dashboard.
    """
    if state == "green":
        return "ok"
    if state in ("orange", "grey"):
        return "warn"
    return "down"  # red


def _run_one(target: dict) -> dict:
    """Run a single probe + classify; any unexpected exception becomes
    GREY for that lamp so a single buggy probe cannot poison the snapshot."""
    try:
        raw = run_probe(target)
        return classify(raw, target)
    except Exception as exc:  # noqa: BLE001 — last line of defence
        return {
            "id": target.get("id", "?"),
            "label": target.get("label", target.get("id", "?")),
            "type": target.get("type", "?"),
            "category": target.get("category", "edge"),
            "critical": bool(target.get("critical", False)),
            "optional": bool(target.get("optional", False)),
            "status_code": None,
            "latency_ms": 0,
            "ok": False,
            "error": f"snapshot guard: {str(exc)[:80]}",
            "meta": {},
            "state": "grey",
            "reason": f"probe crashed: {str(exc)[:80]}",
            "action": "investigate probe internals",
        }


def build_snapshot() -> dict:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Parallel execution. Each probe enforces its own timeout internally;
    # we don't impose a second timeout on the Future because doing so could
    # leak threads. Workers tuned to keep total wall time < 5 s with 53
    # lamps where most probes complete < 100 ms.
    services: list[dict] = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(_run_one, t): t for t in TARGETS}
        for fut in as_completed(futures):
            services.append(fut.result())

    # Re-order to match TARGETS declaration so the UI is deterministic.
    by_id = {s["id"]: s for s in services}
    services = [by_id[t["id"]] for t in TARGETS if t["id"] in by_id]

    green = sum(1 for s in services if s["state"] == "green")
    orange = sum(1 for s in services if s["state"] == "orange")
    red = sum(1 for s in services if s["state"] == "red")
    grey = sum(1 for s in services if s["state"] == "grey")

    if red > 0:
        overall = "down"
    elif orange > 0:
        overall = "warn"
    elif grey > 0:
        # GREY only → soft warn so operators see something is unknown.
        overall = "warn"
    else:
        overall = "ok"

    alerts: list[dict] = []
    for s in services:
        if s["state"] == "red":
            alerts.append({
                "service": s["label"],
                "message": s.get("reason", "failure"),
                "action_hint": s.get("action") or "investigate",
                "severity": "down",
            })
        elif s["state"] == "orange":
            alerts.append({
                "service": s["label"],
                "message": s.get("reason", "degraded"),
                "action_hint": s.get("action") or "monitor",
                "severity": "warn",
            })

    categories: dict[str, list[dict]] = {
        "infrastructure": [],
        "external_apis": [],
        "data_quality": [],
        "workers": [],
    }
    for s in services:
        item = {
            "name": s["label"],
            "status": _legacy_status(s["state"]),
            "detail": s.get("reason", ""),
            "latency": s.get("latency_ms"),
            "critical": bool(s.get("critical", False)),
            "last_check": now_iso,
            # Additive fields (do not break the legacy frontend):
            "category": s.get("category", "edge"),
            "raw_state": s["state"],
        }
        categories[_bucket_for(s.get("category", "edge"))].append(item)

    # Phase 4A: DRY-RUN remediation suggestions. Pure read-only logic;
    # this call NEVER executes anything — it only inspects `services`
    # and returns informational dicts. See remediator.py.
    suggestions = compute_suggestions(services)

    return {
        "timestamp": now_iso,
        "uptime": "LIVE",
        "global": {
            "status": overall,
            "ok_count": green,
            "warn_count": orange + grey,
            "down_count": red,
            "total": len(services),
        },
        "alerts": alerts,
        "categories": categories,
        "remediation": {
            "mode": "dry-run",
            "execution_mode": "controlled",   # PHASE 4C.1
            "suggestions": suggestions,
        },
    }
