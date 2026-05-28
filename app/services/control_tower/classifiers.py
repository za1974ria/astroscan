"""AstroScan Control Tower — Classifier (Phase 3A).

State machine: GREEN / ORANGE / RED / GREY.

Rules (synthetic):
  - measurement failed AND target is critical    → RED
  - measurement failed AND target is non-critical → GREY
  - optional target + 404/403/401                → GREY
  - 5xx                                          → RED
  - 4xx (non-optional, not 401/403)              → RED
  - JSON sanity broken (parse / missing keys)    → ORANGE / RED
  - latency > 2000 ms                            → ORANGE
  - TLS expiry < 7d → RED, < 30d → ORANGE
  - sys cpu/ram/disk/inode ≥ crit → RED, ≥ warn → ORANGE
  - load avg ratio ≥ 4× cores → RED, ≥ 2× → ORANGE
  - everything else (2xx within SLO, healthy)    → GREEN

classify() is pure — takes (result, target) and returns a NEW dict.
"""
from __future__ import annotations


def _grey(r: dict, reason: str, action: str | None = None) -> dict:
    return {**r, "state": "grey", "reason": reason,
            "action": action or "verify configuration / discoverability"}


def _red(r: dict, reason: str, action: str | None = None) -> dict:
    return {**r, "state": "red", "reason": reason,
            "action": action or "investigate immediately"}


def _orange(r: dict, reason: str, action: str | None = None) -> dict:
    return {**r, "state": "orange", "reason": reason,
            "action": action or "monitor closely"}


def _green(r: dict, reason: str = "healthy") -> dict:
    return {**r, "state": "green", "reason": reason, "action": None}


# ── HTTP / JSON sanity ───────────────────────────────────────────────
def _classify_http(r: dict) -> dict:
    optional = bool(r.get("optional", False))
    critical = bool(r.get("critical", False))
    code = r.get("status_code")
    latency = int(r.get("latency_ms") or 0)
    err = r.get("error")
    meta = r.get("meta") or {}

    # No HTTP response at all (timeout, DNS, conn refused, TLS handshake).
    if code is None:
        msg = err or "no response"
        if critical:
            return _red(r, msg, "check connectivity / DNS / upstream")
        return _grey(r, f"unreachable: {msg}")

    # Optional endpoint absent or restricted → soft.
    if optional and code in (401, 403, 404):
        reason = ("optional endpoint not deployed (404)" if code == 404
                  else f"optional endpoint restricted ({code})")
        return _grey(r, reason)

    # JSON sanity checks (apply before generic 2xx path).
    if r.get("type") == "json_sanity":
        if meta.get("json_ok") is False:
            return _red(
                r,
                f"payload not JSON: {meta.get('json_error', '?')}",
                "inspect endpoint response format",
            )
        missing = meta.get("missing_keys") or []
        if missing:
            return _orange(
                r,
                f"missing JSON keys: {','.join(missing)}",
                "verify upstream contract",
            )

    # Plain http min_bytes guard.
    if r.get("type") == "http" and meta.get("too_small"):
        return _orange(
            r,
            f"response too small ({meta.get('size_bytes')} < "
            f"{meta.get('expected_min_bytes')} bytes)",
            "inspect page rendering / blueprint",
        )

    if 200 <= code < 300:
        if latency > 2000:
            return _orange(r, f"slow ({latency} ms)",
                           "inspect upstream performance")
        return _green(r)

    if code in (401, 403):
        return _red(r, f"access blocked ({code})",
                    "check nginx ACL / routing policy")

    if code == 404:
        return _red(r, "not found (404)",
                    "endpoint missing / route deleted")

    if code >= 500:
        return _red(r, f"server failure ({code})",
                    "check backend service / logs")

    return _orange(r, f"unexpected status ({code})",
                   "inspect endpoint behavior")


# ── DNS ──────────────────────────────────────────────────────────────
def _classify_dns(r: dict) -> dict:
    if r.get("error"):
        if r.get("critical"):
            return _red(r, r["error"], "fix DNS / resolver")
        return _grey(r, r["error"])
    if int(r.get("latency_ms") or 0) > 2000:
        return _orange(
            r,
            f"slow DNS ({r['latency_ms']} ms)",
            "check resolver",
        )
    meta = r.get("meta") or {}
    return _green(r, f"resolved {meta.get('resolved_ip', '?')}")


# ── TLS ──────────────────────────────────────────────────────────────
def _classify_tls(r: dict) -> dict:
    if r.get("error"):
        if r.get("critical"):
            return _red(r, r["error"], "renew or fix TLS")
        return _grey(r, r["error"])
    meta = r.get("meta") or {}
    days = meta.get("days_left")
    if days is None:
        return _grey(r, "unknown TLS expiry")
    if days < 0:
        return _red(r, "TLS certificate expired",
                    "renew certificate now")
    if days < 7:
        return _red(r, f"TLS expires in {days} days",
                    "renew certificate within 7 days")
    if days < 30:
        return _orange(r, f"TLS expires in {days} days",
                       "schedule renewal")
    return _green(r, f"TLS valid {days} days")


# ── System metric ────────────────────────────────────────────────────
def _classify_system_metric(r: dict, target: dict) -> dict:
    if r.get("error"):
        if r.get("critical"):
            # Inability to read a critical metric is a real signal of host
            # trouble, but it's safer to keep operators looking than to
            # cascade RED across the dashboard. Mark ORANGE.
            return _orange(r, r["error"], "metric collector unavailable")
        return _grey(r, r["error"])
    meta = r.get("meta") or {}

    metric = target.get("metric")
    if metric in ("cpu", "ram", "disk", "inode"):
        pct = meta.get("pct")
        if pct is None:
            return _grey(r, "metric unreadable")
        warn = float(target.get("warn_pct", 80))
        crit = float(target.get("crit_pct", 90))
        path = meta.get("path")
        label = f"{pct} %"
        if path:
            label += f" ({path}, {meta.get('free_gb', '?')} GB free)" if metric == "disk" else f" ({path})"
        if pct >= crit:
            return _red(r, label, "investigate resource pressure")
        if pct >= warn:
            return _orange(r, label, "monitor — approaching threshold")
        return _green(r, label)

    if metric == "load":
        la1 = meta.get("la1") or 0.0
        cores = meta.get("cores") or 1
        ratio = la1 / cores if cores else 0.0
        if ratio >= 4:
            return _red(
                r,
                f"load {la1} (≥{4 * cores} on {cores}c)",
                "check CPU saturation / runaway",
            )
        if ratio >= 2:
            return _orange(
                r,
                f"load {la1} (≥{2 * cores} on {cores}c)",
                "monitor — high load",
            )
        return _green(r, f"load {la1} on {cores}c")

    return _grey(r, f"unknown metric: {metric}")


# ── Process ──────────────────────────────────────────────────────────
def _classify_process(r: dict) -> dict:
    meta = r.get("meta") or {}
    count = int(meta.get("count", 0))
    name = meta.get("name", "?")
    if r.get("error"):
        if r.get("critical"):
            return _red(r, r["error"], "investigate /proc scan")
        return _grey(r, r["error"])
    if count > 0:
        return _green(r, f"{count} process(es) alive ({name})")
    if r.get("optional") or not r.get("critical"):
        return _grey(r, f"process {name} not found")
    return _red(r, f"process {name} not running",
                "start / restart the service")


# ── Path readable ────────────────────────────────────────────────────
def _classify_path(r: dict, target: dict) -> dict:
    if r.get("error"):
        if r.get("critical"):
            return _red(r, r["error"], "check filesystem permissions")
        return _grey(r, r["error"])
    meta = r.get("meta") or {}
    path = meta.get("path", "?")
    if not meta.get("exists"):
        if r.get("optional") or not r.get("critical"):
            return _grey(r, f"path {path} not present")
        return _red(r, f"path {path} missing",
                    "verify deployment / restore path")
    if not meta.get("readable"):
        if r.get("critical"):
            return _red(r, f"path {path} not readable",
                        "check permissions")
        return _grey(r, f"path {path} not readable")
    # Optional staleness check
    age = meta.get("age_seconds")
    max_age = target.get("max_age_s")
    if age is not None and max_age and age > int(max_age):
        return _orange(
            r,
            f"stale (age {age}s > {max_age}s)",
            "trigger refresh / check producer",
        )
    return _green(r, f"path OK ({path})")


# ── SQLite readable ──────────────────────────────────────────────────
def _classify_sqlite(r: dict) -> dict:
    code = r.get("status_code")
    if code == 404:
        if r.get("optional") or not r.get("critical"):
            return _grey(r, r.get("error") or "db absent")
        return _red(r, r.get("error") or "db not found",
                    "verify deployment / initialize db")
    if r.get("error"):
        if r.get("critical"):
            return _red(r, r["error"], "check sqlite file / corruption")
        return _grey(r, r["error"])
    meta = r.get("meta") or {}
    if meta.get("select_ok"):
        return _green(
            r,
            f"sqlite OK ({meta.get('table_count', 0)} tables)",
        )
    return _red(r, "sqlite select failed", "investigate db integrity")


# ── Public dispatcher ────────────────────────────────────────────────
def classify(result: dict, target: dict | None = None) -> dict:
    """Classify a probe result into a state {green, orange, red, grey}.

    Args:
        result: dict returned by run_probe()
        target: original target dict (used for thresholds like warn_pct,
                crit_pct, max_age_s, metric). May be None for legacy callers.

    Returns:
        A NEW dict (does not mutate `result`) with extra keys:
            state  : "green" | "orange" | "red" | "grey"
            reason : short human-readable detail
            action : short hint (string or None for GREEN)
    """
    t = result.get("type")
    target = target or {}

    if t in ("http", "json_sanity"):
        return _classify_http(result)
    if t == "dns":
        return _classify_dns(result)
    if t == "tls":
        return _classify_tls(result)
    if t == "system_metric":
        return _classify_system_metric(result, target)
    if t == "process":
        return _classify_process(result)
    if t == "path_readable":
        return _classify_path(result, target)
    if t == "sqlite_readable":
        return _classify_sqlite(result)

    return _grey(result, f"unknown probe type {t!r}")
