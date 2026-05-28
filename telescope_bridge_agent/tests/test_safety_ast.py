"""CI safety test — refuses any forbidden operation verb appearing as
an executable Python identifier (function name, class name, attribute
access, variable, keyword arg) anywhere in the agent package.

Allowed exceptions: a small whitelist of state-predicate identifiers
(snake_case booleans describing observed state, not actions).
"""
from __future__ import annotations

import ast
import pathlib


FORBIDDEN = {"slew", "park", "goto", "move", "pulse", "sync", "motor"}

# Read-state predicates — substring match would otherwise flag these
# legitimate snake_case observation booleans.
SAFE_PREDICATES = {
    "is_slewing", "is_parked", "is_moving",
    "is_at_park", "is_at_home", "is_tracking",
    "slewing_state", "parking_state",
}

PKG = pathlib.Path(__file__).resolve().parent.parent / "astroscan_bridge"


def _violation(identifier: str) -> str | None:
    low = identifier.lower()
    if low in SAFE_PREDICATES:
        return None
    for w in FORBIDDEN:
        if w in low:
            return w
    return None


def _scan(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        targets: list[tuple[str, str]] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            targets.append(("def", node.name))
        if isinstance(node, ast.Attribute):
            targets.append(("attr", node.attr))
        if isinstance(node, ast.Name):
            targets.append(("name", node.id))
        if isinstance(node, ast.keyword) and node.arg:
            targets.append(("kwarg", node.arg))
        for kind, n in targets:
            hit = _violation(n)
            if hit is not None:
                bad.append(f"{kind} {n!r} (contains {hit!r}) at L{node.lineno}")
    return bad


def test_no_forbidden_operation_identifiers():
    failures: dict[str, list[str]] = {}
    for py in PKG.rglob("*.py"):
        bad = _scan(py)
        if bad:
            failures[str(py)] = bad
    assert not failures, (
        "forbidden operation verbs detected as executable identifiers:\n"
        + "\n".join(f"  {p}: {b}" for p, b in failures.items())
    )


def test_no_http_write_helpers_in_alpaca():
    """The Alpaca adapter must not import requests.put / .post / .patch."""
    src = (PKG / "adapters" / "alpaca.py").read_text(encoding="utf-8")
    forbidden_calls = ("requests.put", "requests.post", "requests.patch",
                       "requests.delete")
    for call in forbidden_calls:
        assert call not in src, f"alpaca.py must not call {call}"
