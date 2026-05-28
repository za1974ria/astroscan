"""Control Tower — declarative target registry loader.

Reads `targets.yaml` colocated with this module, validates it against
a strict schema, and returns immutable Target dataclasses.

Design contracts (V1):
- Pure module. No Flask import. No network. No side effects on import.
- Single public entrypoint: load_registry(path=None) -> Registry.
- Schema validation is strict: unknown keys raise RegistryError so we
  catch typos at boot instead of silently dropping them.
- Probes referenced here ("process_systemd", "http_edge", "http_internal",
  "frontend_smoke") are NOT executed by this module. Adapter
  implementations land in patch #2+.

Why YAML and not Python dict:
- Editable by non-developers (ops, on-call).
- Diff-friendly in PRs.
- Same source-of-truth file can later be hot-reloaded.

Failure mode:
- Any schema violation raises RegistryError with the offending target
  key in the message. Caller decides whether to fail boot or degrade.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_YAML = Path(__file__).resolve().parent / "targets.yaml"

# Allowed enums — extend as adapters land.
_ALLOWED_PROBES = {
    "http_edge",
    "http_internal",
    "process_systemd",
    "frontend_smoke",
    "tcp_socket",
    "file_freshness",
}
_ALLOWED_CATEGORIES = {"core", "api", "data", "worker", "external"}
_ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}

_TARGET_REQUIRED_KEYS = {"key", "category", "name", "probe", "target"}
_TARGET_OPTIONAL_KEYS = {
    "slo_ms",
    "timeout_ms",
    "severity",
    "enabled",
    "description",
    "expect",
}
_TARGET_ALLOWED_KEYS = _TARGET_REQUIRED_KEYS | _TARGET_OPTIONAL_KEYS


class RegistryError(ValueError):
    """Raised when targets.yaml is malformed or violates the schema."""


@dataclass(frozen=True)
class Target:
    """Immutable monitored target descriptor.

    Attributes:
        key:         Stable unique identifier (e.g. "api.sentinel.health").
        category:    One of _ALLOWED_CATEGORIES.
        name:        Human-readable label shown in dashboards.
        probe:       Adapter id; must be in _ALLOWED_PROBES.
        target:      Probe-specific addressing (URL, systemd unit, host:port).
        slo_ms:      Latency threshold; above it -> ORANGE (degraded).
        timeout_ms:  Absolute cutoff; above it -> RED (failure).
        severity:    Used for alert routing prioritization.
        enabled:     Disabled targets are returned as GREY in snapshots.
        description: Optional human context.
        expect:      Adapter-specific expected-response shape.
    """
    key: str
    category: str
    name: str
    probe: str
    target: str
    slo_ms: int = 800
    timeout_ms: int = 5000
    severity: str = "medium"
    enabled: bool = True
    description: str = ""
    expect: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Registry:
    """Loaded registry snapshot. Immutable; reload by calling load_registry() again."""
    schema_version: int
    source_path: str
    targets: tuple[Target, ...]

    def by_key(self, key: str) -> Target | None:
        for t in self.targets:
            if t.key == key:
                return t
        return None

    def by_category(self, category: str) -> tuple[Target, ...]:
        return tuple(t for t in self.targets if t.category == category)


def _apply_defaults(target_raw: dict, defaults: dict) -> dict:
    merged = dict(defaults)
    merged.update(target_raw)
    return merged


def _validate_target(raw: dict, index: int) -> Target:
    keys = set(raw.keys())
    missing = _TARGET_REQUIRED_KEYS - keys
    if missing:
        raise RegistryError(
            f"target[{index}]: missing required keys {sorted(missing)}"
        )
    unknown = keys - _TARGET_ALLOWED_KEYS
    if unknown:
        raise RegistryError(
            f"target[{index}] key={raw.get('key', '?')!r}: unknown keys "
            f"{sorted(unknown)} (allowed: {sorted(_TARGET_ALLOWED_KEYS)})"
        )
    if raw["probe"] not in _ALLOWED_PROBES:
        raise RegistryError(
            f"target[{index}] key={raw['key']!r}: probe={raw['probe']!r} "
            f"not in {sorted(_ALLOWED_PROBES)}"
        )
    if raw["category"] not in _ALLOWED_CATEGORIES:
        raise RegistryError(
            f"target[{index}] key={raw['key']!r}: category={raw['category']!r} "
            f"not in {sorted(_ALLOWED_CATEGORIES)}"
        )
    sev = raw.get("severity", "medium")
    if sev not in _ALLOWED_SEVERITIES:
        raise RegistryError(
            f"target[{index}] key={raw['key']!r}: severity={sev!r} "
            f"not in {sorted(_ALLOWED_SEVERITIES)}"
        )
    if not isinstance(raw["key"], str) or not raw["key"]:
        raise RegistryError(f"target[{index}]: key must be a non-empty string")
    slo = int(raw.get("slo_ms", 800))
    tmo = int(raw.get("timeout_ms", 5000))
    if slo <= 0 or tmo <= 0:
        raise RegistryError(
            f"target[{index}] key={raw['key']!r}: slo_ms/timeout_ms must be > 0"
        )
    if slo > tmo:
        raise RegistryError(
            f"target[{index}] key={raw['key']!r}: slo_ms ({slo}) cannot exceed "
            f"timeout_ms ({tmo})"
        )
    return Target(
        key=raw["key"],
        category=raw["category"],
        name=raw["name"],
        probe=raw["probe"],
        target=raw["target"],
        slo_ms=slo,
        timeout_ms=tmo,
        severity=sev,
        enabled=bool(raw.get("enabled", True)),
        description=str(raw.get("description", "")),
        expect=dict(raw.get("expect", {})),
    )


def load_registry(path: str | os.PathLike | None = None) -> Registry:
    """Load and validate the target registry.

    Args:
        path: Optional override of the YAML location. Defaults to
              `app/services/control_tower/targets.yaml`.

    Returns:
        Immutable Registry with the parsed targets tuple.

    Raises:
        RegistryError: if file is missing, empty, malformed, has duplicate
                       keys, or any target violates the schema.
    """
    src = Path(path) if path is not None else _DEFAULT_YAML
    if not src.exists():
        raise RegistryError(f"targets file not found: {src}")
    try:
        raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"YAML parse error in {src}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RegistryError(f"{src}: top-level must be a mapping")

    schema_version = int(raw.get("schema_version", 0))
    if schema_version != 1:
        raise RegistryError(
            f"{src}: unsupported schema_version={schema_version} (expected 1)"
        )

    defaults = raw.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise RegistryError(f"{src}: 'defaults' must be a mapping")

    targets_raw = raw.get("targets") or []
    if not isinstance(targets_raw, list) or not targets_raw:
        raise RegistryError(f"{src}: 'targets' must be a non-empty list")

    seen_keys: set[str] = set()
    parsed: list[Target] = []
    for i, t in enumerate(targets_raw):
        if not isinstance(t, dict):
            raise RegistryError(f"target[{i}]: must be a mapping, got {type(t).__name__}")
        merged = _apply_defaults(t, defaults)
        parsed_t = _validate_target(merged, i)
        if parsed_t.key in seen_keys:
            raise RegistryError(
                f"target[{i}]: duplicate key={parsed_t.key!r}"
            )
        seen_keys.add(parsed_t.key)
        parsed.append(parsed_t)

    return Registry(
        schema_version=schema_version,
        source_path=str(src),
        targets=tuple(parsed),
    )
