"""Guardian health collectors — read-only probes of the system.

Each collector returns a dict::

    {
      "name": "<collector_name>",
      "ok": bool,           # True if probe succeeded (regardless of metric severity)
      "value": {...},       # collector-specific payload
      "severity": "info|warn|critical",
      "ts": "<iso8601>",
      "latency_ms": int
    }

Hard rules:
    - NEVER use shell=True.
    - subprocess is invoked with args=[...] (list) only.
    - No mutating commands (systemctl is-active, not start/stop/restart).
    - Each collector wraps its body in try/except → returns {"ok": False, ...}
      rather than letting an exception escape.
    - Probes have hard timeouts (~5s) to avoid blocking the monitoring thread.
"""
from __future__ import annotations

import logging
import os
import re
import socket
import ssl
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

log = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Default thresholds — also referenced by config/guardian_rules.yaml at runtime.
_DISK_WARN_PCT = 80
_DISK_CRITICAL_PCT = 90
_RAM_WARN_PCT = 80
_RAM_CRITICAL_PCT = 92
_LOAD_WARN = 4.0
_LOAD_CRITICAL = 8.0
_SSL_DAYS_WARN = 14
_SSL_DAYS_CRITICAL = 3
_HTTP_TIMEOUT_S = 5.0
_SUBPROCESS_TIMEOUT_S = 5
_LOG_PEEK_LINES = 100


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _envelope(
    name: str,
    ok: bool,
    value: dict | None = None,
    severity: str = "info",
    latency_ms: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "ok": ok,
        "value": value or {},
        "severity": severity,
        "ts": _iso_now(),
        "latency_ms": int(latency_ms),
    }
    if error:
        out["error"] = error
    return out


def _safe_subprocess(args: list[str], timeout: float = _SUBPROCESS_TIMEOUT_S) -> tuple[bool, str, str]:
    """Whitelist subprocess wrapper. Returns (ok, stdout, stderr).

    Never uses shell=True. Hard timeout. Captures both streams as text.
    """
    if not args or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return False, "", "invalid_args"
    try:
        cp = subprocess.run(  # noqa: S603 — args list + no shell
            args, capture_output=True, text=True, timeout=timeout, check=False,
        )
        return cp.returncode == 0, cp.stdout or "", cp.stderr or ""
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except FileNotFoundError:
        return False, "", "binary_not_found"
    except Exception as exc:  # noqa: BLE001
        return False, "", f"exception:{type(exc).__name__}"


# ─── 1. systemd unit status ─────────────────────────────────────────────────


def collect_systemd_astroscan() -> dict:
    t0 = time.monotonic()
    ok, out, err = _safe_subprocess(["systemctl", "is-active", "astroscan.service"])
    state = (out or "").strip() or err
    severity = "info" if ok and state == "active" else "critical"
    return _envelope(
        "systemd_astroscan", ok=True,
        value={"active": ok and state == "active", "state": state},
        severity=severity,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── 2. HTTP probe — root + sentinel ────────────────────────────────────────


def _http_probe(url: str, name: str) -> dict:
    t0 = time.monotonic()
    try:
        req = urllib_request.Request(url, method="GET")
        with urllib_request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as r:  # noqa: S310
            code = int(r.status)
        latency_ms = int((time.monotonic() - t0) * 1000)
        sev = "info" if 200 <= code < 400 else "critical"
        return _envelope(
            name, ok=True,
            value={"url": url, "status": code, "latency_ms": latency_ms},
            severity=sev,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _envelope(
            name, ok=False,
            value={"url": url}, severity="critical",
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}",
        )


def collect_http_root() -> dict:
    return _http_probe("http://127.0.0.1:5003/", "http_root")


def collect_http_sentinel_health() -> dict:
    return _http_probe("http://127.0.0.1:5003/api/sentinel/health", "http_sentinel_health")


# ─── 3. Disk ────────────────────────────────────────────────────────────────


def collect_disk(path: str = "/") -> dict:
    t0 = time.monotonic()
    ok, out, err = _safe_subprocess(["df", "-P", path])
    if not ok:
        return _envelope("disk", ok=False, error=err, severity="warn",
                         latency_ms=int((time.monotonic() - t0) * 1000))
    # Filesystem 1024-blocks Used Available Capacity Mounted on
    try:
        lines = out.strip().splitlines()
        if len(lines) < 2:
            raise ValueError("malformed df output")
        parts = lines[1].split()
        capacity_str = parts[4].rstrip("%")
        pct = int(capacity_str)
    except (ValueError, IndexError) as exc:
        return _envelope("disk", ok=False, severity="warn", error=str(exc),
                         latency_ms=int((time.monotonic() - t0) * 1000))

    sev = (
        "critical" if pct >= _DISK_CRITICAL_PCT
        else "warn" if pct >= _DISK_WARN_PCT
        else "info"
    )
    return _envelope(
        "disk", ok=True,
        value={"path": path, "percent_used": pct},
        severity=sev,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── 4. RAM ─────────────────────────────────────────────────────────────────


def collect_ram(meminfo_path: str = "/proc/meminfo") -> dict:
    t0 = time.monotonic()
    try:
        with open(meminfo_path, encoding="utf-8") as f:
            text = f.read()
        m = {}
        for line in text.splitlines():
            k, _, rest = line.partition(":")
            val = rest.strip().split()
            if val:
                m[k.strip()] = int(val[0])
        total = m.get("MemTotal", 0)
        available = m.get("MemAvailable", m.get("MemFree", 0))
        if total == 0:
            raise ValueError("MemTotal=0")
        used = total - available
        pct = round((used / total) * 100, 1)
    except (OSError, ValueError, KeyError) as exc:
        return _envelope("ram", ok=False, severity="warn",
                         error=type(exc).__name__,
                         latency_ms=int((time.monotonic() - t0) * 1000))

    sev = (
        "critical" if pct >= _RAM_CRITICAL_PCT
        else "warn" if pct >= _RAM_WARN_PCT
        else "info"
    )
    return _envelope(
        "ram", ok=True,
        value={"percent_used": pct, "total_kb": total, "available_kb": available},
        severity=sev,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── 5. CPU load ────────────────────────────────────────────────────────────


def collect_cpu_load(loadavg_path: str = "/proc/loadavg") -> dict:
    t0 = time.monotonic()
    try:
        with open(loadavg_path, encoding="utf-8") as f:
            parts = f.read().split()
        l1, l5, l15 = float(parts[0]), float(parts[1]), float(parts[2])
    except (OSError, ValueError, IndexError) as exc:
        return _envelope("cpu_load", ok=False, severity="warn",
                         error=type(exc).__name__,
                         latency_ms=int((time.monotonic() - t0) * 1000))

    sev = (
        "critical" if l5 >= _LOAD_CRITICAL
        else "warn" if l5 >= _LOAD_WARN
        else "info"
    )
    return _envelope(
        "cpu_load", ok=True,
        value={"load_1m": l1, "load_5m": l5, "load_15m": l15},
        severity=sev,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── 6. SSL expiry ──────────────────────────────────────────────────────────


def collect_ssl_expiry(domain: str = "astroscan.space", port: int = 443) -> dict:
    t0 = time.monotonic()
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=_HTTP_TIMEOUT_S) as raw:
            with ctx.wrap_socket(raw, server_hostname=domain) as sock:
                cert = sock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            raise ValueError("notAfter missing in cert")
        expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
        delta = expiry - datetime.now(UTC)
        days = max(0, int(delta.total_seconds() // 86400))
    except Exception as exc:  # noqa: BLE001
        return _envelope("ssl_expiry", ok=False, severity="warn",
                         value={"domain": domain},
                         error=type(exc).__name__,
                         latency_ms=int((time.monotonic() - t0) * 1000))

    sev = (
        "critical" if days < _SSL_DAYS_CRITICAL
        else "warn" if days < _SSL_DAYS_WARN
        else "info"
    )
    return _envelope(
        "ssl_expiry", ok=True,
        value={"domain": domain, "days_until_expiry": days, "expires_at": not_after},
        severity=sev,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── 7. Nginx ───────────────────────────────────────────────────────────────


def collect_nginx() -> dict:
    t0 = time.monotonic()
    ok, out, err = _safe_subprocess(["systemctl", "is-active", "nginx"])
    state = (out or "").strip() or (err or "unknown")
    severity = "info" if ok and state == "active" else "critical"
    return _envelope(
        "nginx", ok=True,
        value={"active": ok and state == "active", "state": state},
        severity=severity,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── 8. Log anomalies (last N lines) ────────────────────────────────────────


def collect_log_anomalies(
    log_file: str | Path | None = None,
    lines: int = _LOG_PEEK_LINES,
) -> dict:
    """Counts ERROR/CRITICAL/500 lines in the last N entries of the structured log."""
    t0 = time.monotonic()
    path = Path(log_file) if log_file else _PROJECT_ROOT / "logs" / "astroscan_structured.log"
    try:
        if not path.exists():
            return _envelope(
                "log_anomalies", ok=True,
                value={"error_count": 0, "critical_count": 0, "http_500_count": 0,
                       "file": str(path), "note": "file_absent"},
                severity="info",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            size = f.tell()
            # Read up to ~256 KB tail
            f.seek(max(0, size - 256 * 1024))
            tail = f.read().splitlines()[-lines:]
        text = "\n".join(tail)
        err_count = len(re.findall(r"\bERROR\b", text))
        crit_count = len(re.findall(r"\bCRITICAL\b", text))
        http500 = len(re.findall(r"\b5\d{2}\b", text))
    except (OSError, ValueError) as exc:
        return _envelope("log_anomalies", ok=False, severity="warn",
                         error=type(exc).__name__,
                         latency_ms=int((time.monotonic() - t0) * 1000))

    sev = (
        "warn" if (err_count > 10 or crit_count > 0 or http500 > 5) else "info"
    )
    return _envelope(
        "log_anomalies", ok=True,
        value={
            "error_count": err_count,
            "critical_count": crit_count,
            "http_500_count_last_100": http500,
            "lines_scanned": len(tail),
            "file": str(path),
        },
        severity=sev,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── 9. Data freshness probes ───────────────────────────────────────────────


def _file_age_seconds(p: Path) -> int | None:
    try:
        mtime = p.stat().st_mtime
        return max(0, int(time.time() - mtime))
    except (OSError, ValueError):
        return None


def collect_iss_feed_freshness(custom_path: str | None = None) -> dict:
    """Probe the last ISS snapshot timestamp (file mtime)."""
    t0 = time.monotonic()
    candidates = [
        Path(custom_path) if custom_path else None,
        _PROJECT_ROOT / "data" / "iss_position.json",
        _PROJECT_ROOT / "data" / "tle" / "active.tle",
    ]
    for p in candidates:
        if p and p.exists():
            age = _file_age_seconds(p)
            sev = "info"
            if age is None:
                sev = "warn"
            elif age > 3600:
                sev = "critical"
            elif age > 1200:
                sev = "warn"
            return _envelope(
                "iss_feed_freshness", ok=True,
                value={"file": str(p), "age_seconds": age},
                severity=sev,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
    return _envelope(
        "iss_feed_freshness", ok=True,
        value={"note": "no_iss_snapshot_file_found", "age_seconds": None},
        severity="warn",
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


def collect_weather_freshness(custom_path: str | None = None) -> dict:
    """Probe last weather feed snapshot file age."""
    t0 = time.monotonic()
    candidates = [
        Path(custom_path) if custom_path else None,
        _PROJECT_ROOT / "data" / "weather_snapshot.json",
        _PROJECT_ROOT / "data" / "noaa_kp.json",
    ]
    for p in candidates:
        if p and p.exists():
            age = _file_age_seconds(p)
            sev = "info"
            if age is None:
                sev = "warn"
            elif age > 7200:
                sev = "warn"
            return _envelope(
                "weather_freshness", ok=True,
                value={"file": str(p), "age_seconds": age},
                severity=sev,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
    return _envelope(
        "weather_freshness", ok=True,
        value={"note": "no_weather_snapshot_file_found", "age_seconds": None},
        severity="info",
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# ─── Aggregator ─────────────────────────────────────────────────────────────


ALL_COLLECTORS = [
    collect_systemd_astroscan,
    collect_http_root,
    collect_http_sentinel_health,
    collect_disk,
    collect_ram,
    collect_cpu_load,
    collect_nginx,
    collect_log_anomalies,
    collect_iss_feed_freshness,
    collect_weather_freshness,
    # ssl_expiry is skipped from the default aggregate — it's network-dependent
    # and slow. Use the dedicated route or schedule it separately.
]


def collect_all() -> list[dict]:
    """Run every default collector and return their results. Each collector
    is independently try/except-wrapped so one failure doesn't kill the batch."""
    out: list[dict] = []
    for fn in ALL_COLLECTORS:
        try:
            out.append(fn())
        except Exception as exc:  # noqa: BLE001
            out.append(_envelope(
                getattr(fn, "__name__", "unknown"), ok=False,
                severity="warn", error=f"collector_crashed:{type(exc).__name__}",
            ))
    return out


__all__ = [
    "ALL_COLLECTORS",
    "collect_all",
    "collect_cpu_load",
    "collect_disk",
    "collect_http_root",
    "collect_http_sentinel_health",
    "collect_iss_feed_freshness",
    "collect_log_anomalies",
    "collect_nginx",
    "collect_ram",
    "collect_ssl_expiry",
    "collect_systemd_astroscan",
    "collect_weather_freshness",
]
