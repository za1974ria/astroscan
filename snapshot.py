from datetime import datetime, timezone

from app.services.control_tower.targets import TARGETS
from app.services.control_tower.probes import run_probe
from app.services.control_tower.classifiers import classify


def _legacy_status(state):
    if state == "green":
        return "ok"
    if state == "orange":
        return "warn"
    return "down"


def build_snapshot():
    now = datetime.now(timezone.utc)
    services = []

    for target in TARGETS:
        raw = run_probe(target)
        classified = classify(raw)
        services.append(classified)

    green = sum(1 for s in services if s["state"] == "green")
    orange = sum(1 for s in services if s["state"] == "orange")
    red = sum(1 for s in services if s["state"] == "red")
    grey = sum(1 for s in services if s["state"] == "grey")

    overall = "ok"
    if red > 0:
        overall = "down"
    elif orange > 0:
        overall = "warn"

    alerts = []
    for s in services:
        if s["state"] in ("red", "orange"):
            alerts.append({
                "service": s["label"],
                "message": s["reason"],
                "action_hint": s["action"] or "monitor",
                "severity": "down" if s["state"] == "red" else "warn",
            })

    categories = {
        "infrastructure": [],
        "external_apis": [],
        "data_quality": [],
        "workers": [],
    }

    for s in services:
        categories["infrastructure"].append({
            "name": s["label"],
            "status": _legacy_status(s["state"]),
            "detail": s["reason"],
            "latency": s["latency_ms"],
            "critical": s["critical"],
            "last_check": now.isoformat(),
        })

    return {
        "timestamp": now.isoformat(),
        "uptime": "LIVE",
        "global": {
            "status": overall,
            "ok_count": green,
            "warn_count": orange,
            "down_count": red,
            "total": len(services),
        },
        "alerts": alerts,
        "categories": categories,
    }
