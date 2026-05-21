"""Unit tests — guardian.rules evaluator + cooldown."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.blueprints.guardian.rules import (
    Rule,
    _lookup_metric,
    evaluate,
    load_rules,
)

pytestmark = pytest.mark.unit


# ─── load_rules ─────────────────────────────────────────────────────────────


def test_load_rules_default_file_loads_at_least_one():
    rules = load_rules()
    assert isinstance(rules, list)
    # config/guardian_rules.yaml ships with 15 rules
    assert len(rules) >= 5
    assert all(isinstance(r, Rule) for r in rules)


def test_load_rules_missing_file_returns_empty(tmp_path):
    rules = load_rules(tmp_path / "no_such.yaml")
    assert rules == []


def test_load_rules_malformed_yaml_returns_empty(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: a list - of rules\n   :: weird")
    rules = load_rules(bad)
    assert rules == []


def test_load_rules_skips_malformed_entry(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("""
rules:
  - name: good
    metric: disk.percent_used
    operator: ">"
    threshold: 80
    severity: warn
  - {bad_entry_missing_required: fields}
""")
    rules = load_rules(p)
    assert len(rules) == 1
    assert rules[0].name == "good"


# ─── _lookup_metric ─────────────────────────────────────────────────────────


def _snap(name, value, ok=True):
    return {"name": name, "ok": ok, "value": value, "severity": "info"}


def test_lookup_metric_flat():
    snaps = {"disk": _snap("disk", {"percent_used": 75})}
    assert _lookup_metric(snaps, "disk.percent_used") == 75


def test_lookup_metric_missing_collector():
    assert _lookup_metric({}, "x.y") is None


def test_lookup_metric_collector_not_ok():
    snaps = {"disk": _snap("disk", {"percent_used": 75}, ok=False)}
    assert _lookup_metric(snaps, "disk.percent_used") is None


def test_lookup_metric_missing_field():
    snaps = {"disk": _snap("disk", {"percent_used": 75})}
    assert _lookup_metric(snaps, "disk.nope") is None


def test_lookup_metric_no_dot():
    assert _lookup_metric({}, "no_dot") is None


# ─── evaluate ───────────────────────────────────────────────────────────────


def _make_rule(**overrides):
    base = {"name": "r1", "metric": "disk.percent_used", "operator": ">",
            "threshold": 80, "severity": "warn", "cooldown_minutes": 5}
    base.update(overrides)
    return Rule(**base)


def test_evaluate_no_match():
    rules = [_make_rule(threshold=90)]
    snaps = [_snap("disk", {"percent_used": 50})]
    incidents, cool = evaluate(rules, snaps)
    assert incidents == []
    assert cool == {}


def test_evaluate_match_fires_incident():
    rules = [_make_rule(threshold=80)]
    snaps = [_snap("disk", {"percent_used": 95})]
    incidents, cool = evaluate(rules, snaps)
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.rule == "r1"
    assert inc.severity == "warn"
    assert inc.actual == 95
    assert "r1" in cool


def test_evaluate_cooldown_blocks_second_fire():
    rules = [_make_rule(threshold=80, cooldown_minutes=10)]
    snaps = [_snap("disk", {"percent_used": 95})]
    now = datetime(2026, 5, 21, 20, 0, tzinfo=UTC)
    incidents1, cool1 = evaluate(rules, snaps, cooldown_state={}, now=now)
    assert len(incidents1) == 1

    # Same tick → would re-fire if cooldown empty, but cool1 set the until.
    incidents2, cool2 = evaluate(rules, snaps, cooldown_state=cool1, now=now + timedelta(minutes=5))
    assert incidents2 == []  # still in cooldown


def test_evaluate_cooldown_expires_allows_fire():
    rules = [_make_rule(threshold=80, cooldown_minutes=5)]
    snaps = [_snap("disk", {"percent_used": 95})]
    now = datetime(2026, 5, 21, 20, 0, tzinfo=UTC)
    _, cool = evaluate(rules, snaps, cooldown_state={}, now=now)
    later = now + timedelta(minutes=10)
    incidents, _ = evaluate(rules, snaps, cooldown_state=cool, now=later)
    assert len(incidents) == 1


def test_evaluate_equality_operator_bool():
    rules = [Rule(name="down", metric="svc.active", operator="==",
                  value=False, severity="critical")]
    snaps = [_snap("svc", {"active": False})]
    incidents, _ = evaluate(rules, snaps)
    assert len(incidents) == 1
    assert incidents[0].severity == "critical"


def test_evaluate_equality_no_match():
    rules = [Rule(name="down", metric="svc.active", operator="==",
                  value=False, severity="critical")]
    snaps = [_snap("svc", {"active": True})]
    incidents, _ = evaluate(rules, snaps)
    assert incidents == []


def test_evaluate_numeric_op_lt():
    rules = [Rule(name="ssl", metric="ssl.days", operator="<", threshold=14, severity="warn")]
    snaps = [_snap("ssl", {"days": 5})]
    incidents, _ = evaluate(rules, snaps)
    assert len(incidents) == 1


def test_evaluate_invalid_op_silently_skipped():
    rules = [Rule(name="weird", metric="x.y", operator="?@*", threshold=1)]
    snaps = [_snap("x", {"y": 999})]
    incidents, _ = evaluate(rules, snaps)
    assert incidents == []


def test_evaluate_missing_threshold_for_numeric_silently_skipped():
    rules = [Rule(name="r", metric="x.y", operator=">")]
    snaps = [_snap("x", {"y": 5})]
    incidents, _ = evaluate(rules, snaps)
    assert incidents == []


def test_evaluate_non_numeric_actual_silently_skipped():
    rules = [_make_rule(metric="x.y", threshold=10)]
    snaps = [_snap("x", {"y": "not-a-number"})]
    incidents, _ = evaluate(rules, snaps)
    assert incidents == []


def test_evaluate_metric_absent_silently_skipped():
    rules = [_make_rule(metric="absent.missing", threshold=10)]
    snaps = [_snap("other", {"x": 1})]
    incidents, _ = evaluate(rules, snaps)
    assert incidents == []


def test_evaluate_multiple_rules_independent():
    rules = [
        _make_rule(name="A", metric="disk.percent_used", threshold=70),
        _make_rule(name="B", metric="disk.percent_used", threshold=90),
    ]
    snaps = [_snap("disk", {"percent_used": 80})]
    incidents, _ = evaluate(rules, snaps)
    assert len(incidents) == 1
    assert incidents[0].rule == "A"
