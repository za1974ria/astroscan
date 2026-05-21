"""Guardian rules engine — pure logic, no I/O.

Loads rules from config/guardian_rules.yaml, evaluates them against a
snapshot of collector results, and enforces cooldown windows.

Public surface:
    load_rules(path=None) -> list[Rule]
    evaluate(rules, snapshots, cooldown_state, now=None) -> list[Incident]
    Incident dataclass
    Rule dataclass

The evaluator is intentionally pure: it takes the cooldown state as an
input argument and returns the new state implicitly via the incidents'
``next_cooldown_until`` field. The agent thread is responsible for
threading that state across ticks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_RULES_PATH = _PROJECT_ROOT / "config" / "guardian_rules.yaml"

# Operators kept narrow on purpose — easier to audit.
_NUMERIC_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}
_EQUALITY_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@dataclass
class Rule:
    name: str
    metric: str  # dotted path, e.g. "disk.percent_used"
    operator: str
    severity: str = "warn"
    cooldown_minutes: int = 30
    threshold: float | None = None
    value: Any | None = None  # for == / != comparisons


@dataclass
class Incident:
    rule: str
    severity: str
    metric: str
    operator: str
    threshold: float | None
    actual: Any
    ts: str
    cooldown_until: str  # ISO8601


# ─── Loading ────────────────────────────────────────────────────────────────


def load_rules(path: str | Path | None = None) -> list[Rule]:
    """Load and validate rules from a YAML file.

    YAML is optional — if missing or invalid, return an empty list and log
    a warning rather than crashing the agent.
    """
    rules_path = Path(path) if path else _DEFAULT_RULES_PATH
    if not rules_path.exists():
        log.warning("[guardian] rules file not found: %s", rules_path)
        return []
    try:
        import yaml  # noqa: WPS433 — lazy

        with open(rules_path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("[guardian] could not parse rules YAML: %s", exc)
        return []

    raw = doc.get("rules") or []
    rules: list[Rule] = []
    for r in raw:
        try:
            rules.append(Rule(
                name=str(r["name"]),
                metric=str(r["metric"]),
                operator=str(r["operator"]),
                severity=str(r.get("severity", "warn")),
                cooldown_minutes=int(r.get("cooldown_minutes", 30)),
                threshold=float(r["threshold"]) if "threshold" in r and r["threshold"] is not None else None,
                value=r.get("value"),
            ))
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("[guardian] skipping malformed rule %r: %s", r, exc)
    return rules


# ─── Evaluation ─────────────────────────────────────────────────────────────


def _lookup_metric(snapshots: dict[str, dict], dotted: str) -> Any | None:
    """Resolve 'collector.field' from a {name: snapshot} map. Returns None if missing."""
    if "." not in dotted:
        return None
    collector, field_name = dotted.split(".", 1)
    snap = snapshots.get(collector)
    if not snap or not snap.get("ok", False):
        return None
    value = snap.get("value") or {}
    if "." in field_name:
        # Nested access (e.g., disk.subfield.nested)
        for part in field_name.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
    else:
        value = value.get(field_name)
    return value


def _snapshots_map(snapshots: list[dict]) -> dict[str, dict]:
    return {s.get("name", ""): s for s in snapshots if isinstance(s, dict)}


def evaluate(
    rules: list[Rule],
    snapshots: list[dict],
    cooldown_state: dict[str, datetime] | None = None,
    now: datetime | None = None,
) -> tuple[list[Incident], dict[str, datetime]]:
    """Evaluate rules. Returns (incidents_fired, new_cooldown_state).

    Caller is responsible for persisting the cooldown_state across ticks.
    """
    now = now or datetime.now(UTC)
    cooldown_state = dict(cooldown_state or {})
    snap_map = _snapshots_map(snapshots)
    incidents: list[Incident] = []

    for rule in rules:
        # Cooldown check
        until = cooldown_state.get(rule.name)
        if until and now < until:
            continue

        actual = _lookup_metric(snap_map, rule.metric)
        if actual is None:
            continue

        fired = False
        if rule.operator in _NUMERIC_OPS:
            if rule.threshold is None:
                continue
            try:
                fired = _NUMERIC_OPS[rule.operator](float(actual), float(rule.threshold))
            except (TypeError, ValueError):
                continue
        elif rule.operator in _EQUALITY_OPS:
            target = rule.value if rule.value is not None else rule.threshold
            fired = _EQUALITY_OPS[rule.operator](actual, target)

        if fired:
            next_until = now + timedelta(minutes=rule.cooldown_minutes)
            cooldown_state[rule.name] = next_until
            incidents.append(Incident(
                rule=rule.name,
                severity=rule.severity,
                metric=rule.metric,
                operator=rule.operator,
                threshold=rule.threshold,
                actual=actual,
                ts=now.isoformat(),
                cooldown_until=next_until.isoformat(),
            ))

    return incidents, cooldown_state


__all__ = [
    "Incident",
    "Rule",
    "evaluate",
    "load_rules",
]
