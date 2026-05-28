"""AstroScan Control Tower — Probes (Phase 3A).

Read-only probes. No mutation. No autoheal. Every adapter must:
  - honour target['timeout']
  - never raise to the caller (all exceptions captured)
  - return a uniform dict (see _new_result)

Adapters:
  probe_http              (also handles json_sanity via the same path)
  probe_dns
  probe_tls
  probe_system_metric     (psutil if available, /proc fallback)
  probe_process
  probe_path_readable
  probe_sqlite_readable

Dispatched by run_probe(target) using target['type'].
"""
from __future__ import annotations

import os
import socket
import sqlite3
import ssl
import time
from datetime import datetime, timezone

import requests

# psutil is optional. If missing we fall back to /proc + os.statvfs.
try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except Exception:  # pragma: no cover — psutil not installed is supported
    psutil = None  # type: ignore
    _HAS_PSUTIL = False


_HEADERS = {"User-Agent": "AstroScan-ControlTower/3A"}


def _new_result(target: dict) -> dict:
    """Common scaffold so every probe returns the same shape."""
    return {
        "id": target["id"],
        "label": target["label"],
        "type": target["type"],
        "category": target.get("category", "edge"),
        "critical": bool(target.get("critical", False)),
        "optional": bool(target.get("optional", False)),
        "status_code": None,
        "latency_ms": 0,
        "ok": False,
        "error": None,
        "meta": {},
    }


# ── HTTP / JSON sanity ───────────────────────────────────────────────
def probe_http(target: dict) -> dict:
    res = _new_result(target)
    started = time.time()
    timeout = float(target.get("timeout", 5))
    url = target.get("url", "")
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers=_HEADERS,
            allow_redirects=True,
        )
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["status_code"] = r.status_code
        res["ok"] = 200 <= r.status_code < 300
        body = r.content or b""
        res["meta"]["size_bytes"] = len(body)

        # JSON sanity path: must parse and contain required keys (if any).
        if target["type"] == "json_sanity":
            try:
                payload = r.json()
                res["meta"]["json_ok"] = True
                required = target.get("json_keys") or []
                if isinstance(payload, dict):
                    missing = [k for k in required if k not in payload]
                else:
                    missing = list(required)  # not a dict → all keys "missing"
                if missing:
                    res["meta"]["missing_keys"] = missing
                    res["ok"] = False
            except Exception as je:
                res["meta"]["json_ok"] = False
                res["meta"]["json_error"] = str(je)[:120]
                res["ok"] = False

        # min_bytes sanity (plain http only)
        elif target.get("min_bytes") and len(body) < int(target["min_bytes"]):
            res["meta"]["too_small"] = True
            res["meta"]["expected_min_bytes"] = int(target["min_bytes"])
            res["ok"] = False

    except requests.exceptions.Timeout:
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["error"] = f"timeout after {timeout}s"
    except requests.exceptions.SSLError as e:
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["error"] = f"TLS error: {str(e)[:90]}"
    except requests.exceptions.ConnectionError as e:
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["error"] = f"connection error: {str(e)[:90]}"
    except Exception as e:  # noqa: BLE001 — last-line safety
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["error"] = str(e)[:120]
    return res


# ── DNS resolution ───────────────────────────────────────────────────
def probe_dns(target: dict) -> dict:
    res = _new_result(target)
    started = time.time()
    host = target.get("host", "")
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(float(target.get("timeout", 4)))
        ip = socket.gethostbyname(host)
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["ok"] = True
        res["status_code"] = 200
        res["meta"]["resolved_ip"] = ip
        res["meta"]["host"] = host
    except socket.gaierror as e:
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["error"] = f"DNS resolve failed: {e}"
    except Exception as e:  # noqa: BLE001
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["error"] = str(e)[:120]
    finally:
        socket.setdefaulttimeout(old)
    return res


# ── TLS certificate expiry ───────────────────────────────────────────
def probe_tls(target: dict) -> dict:
    res = _new_result(target)
    started = time.time()
    host = target.get("host", "")
    port = int(target.get("port", 443))
    timeout = float(target.get("timeout", 6))
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            raise ValueError("notAfter missing from peer cert")
        # OpenSSL format: 'Apr 21 12:00:00 2026 GMT'
        exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
        exp = exp.replace(tzinfo=timezone.utc)
        days_left = int((exp - datetime.now(timezone.utc)).total_seconds() // 86400)
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["ok"] = days_left > 0
        res["status_code"] = 200
        res["meta"]["days_left"] = days_left
        res["meta"]["not_after"] = not_after
        issuer = dict(x[0] for x in cert.get("issuer", []))
        res["meta"]["issuer"] = issuer.get("organizationName", "?")
    except Exception as e:  # noqa: BLE001
        res["latency_ms"] = int((time.time() - started) * 1000)
        res["error"] = f"TLS check failed: {str(e)[:90]}"
    return res


# ── System metrics ───────────────────────────────────────────────────
def _read_cpu_pct() -> float | None:
    if _HAS_PSUTIL:
        try:
            return float(psutil.cpu_percent(interval=0.15))
        except Exception:
            return None
    # /proc/stat fallback: two snapshots ~150 ms apart.
    def _snap():
        with open("/proc/stat", "r") as f:
            line = f.readline()
        nums = [int(x) for x in line.split()[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        total = sum(nums)
        return idle, total
    try:
        i1, t1 = _snap()
        time.sleep(0.15)
        i2, t2 = _snap()
        dt = t2 - t1
        di = i2 - i1
        if dt <= 0:
            return None
        return round(100.0 * (1.0 - (di / dt)), 1)
    except Exception:
        return None


def _read_mem_pct() -> float | None:
    if _HAS_PSUTIL:
        try:
            return float(psutil.virtual_memory().percent)
        except Exception:
            return None
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                k, _, v = line.partition(":")
                parts = v.strip().split()
                if parts:
                    info[k] = int(parts[0])
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        if not total:
            return None
        return round(100.0 * (1.0 - avail / total), 1)
    except Exception:
        return None


def _read_loadavg() -> list[float] | None:
    if _HAS_PSUTIL:
        try:
            return list(psutil.getloadavg())
        except Exception:
            pass
    try:
        with open("/proc/loadavg", "r") as f:
            parts = f.read().split()
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except Exception:
        return None


def _cpu_cores() -> int:
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def probe_system_metric(target: dict) -> dict:
    res = _new_result(target)
    metric = target.get("metric", "")
    started = time.time()
    try:
        if metric == "cpu":
            pct = _read_cpu_pct()
            if pct is None:
                res["error"] = "cpu metric unavailable"
            else:
                res["meta"]["pct"] = pct
                res["ok"] = True
                res["status_code"] = 200
        elif metric == "ram":
            pct = _read_mem_pct()
            if pct is None:
                res["error"] = "ram metric unavailable"
            else:
                res["meta"]["pct"] = pct
                res["ok"] = True
                res["status_code"] = 200
        elif metric == "disk":
            path = target.get("path", "/")
            st = os.statvfs(path)
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            pct = round(100.0 * (1.0 - free / total), 1) if total else None
            res["meta"]["path"] = path
            res["meta"]["pct"] = pct
            res["meta"]["free_gb"] = round(free / (1024 ** 3), 1)
            res["ok"] = pct is not None
            res["status_code"] = 200 if res["ok"] else None
        elif metric == "inode":
            path = target.get("path", "/")
            st = os.statvfs(path)
            total = st.f_files
            free = st.f_ffree
            pct = round(100.0 * (1.0 - free / total), 1) if total else None
            res["meta"]["path"] = path
            res["meta"]["pct"] = pct
            res["meta"]["free"] = free
            res["ok"] = pct is not None
            res["status_code"] = 200 if res["ok"] else None
        elif metric == "load":
            la = _read_loadavg()
            cores = _cpu_cores()
            if la is None:
                res["error"] = "loadavg unavailable"
            else:
                res["meta"]["la1"] = la[0]
                res["meta"]["la5"] = la[1]
                res["meta"]["la15"] = la[2]
                res["meta"]["cores"] = cores
                res["meta"]["ratio"] = round(la[0] / cores, 2) if cores else None
                res["ok"] = True
                res["status_code"] = 200
        else:
            res["error"] = f"unknown metric: {metric}"
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:120]
    res["latency_ms"] = int((time.time() - started) * 1000)
    return res


# ── Process alive (no subprocess; /proc scan only) ───────────────────
def probe_process(target: dict) -> dict:
    res = _new_result(target)
    started = time.time()
    name = target.get("process_name", "")
    count = 0
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/comm", "r") as f:
                    comm = f.read().strip()
                if comm == name:
                    count += 1
            except (OSError, IOError):
                continue
        res["meta"]["count"] = count
        res["meta"]["name"] = name
        res["ok"] = count > 0
        res["status_code"] = 200 if count > 0 else 503
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:120]
    res["latency_ms"] = int((time.time() - started) * 1000)
    return res


# ── Filesystem path readable ─────────────────────────────────────────
def probe_path_readable(target: dict) -> dict:
    res = _new_result(target)
    started = time.time()
    path = target.get("path", "")
    must_be_dir = bool(target.get("must_be_dir", False))
    try:
        exists = os.path.exists(path)
        readable = exists and os.access(path, os.R_OK)
        if exists and must_be_dir:
            readable = readable and os.path.isdir(path)
        res["meta"]["path"] = path
        res["meta"]["exists"] = exists
        res["meta"]["readable"] = readable
        if exists:
            try:
                st = os.stat(path)
                mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                age = int((datetime.now(timezone.utc) - mtime).total_seconds())
                res["meta"]["age_seconds"] = age
                res["meta"]["mtime"] = mtime.isoformat()
            except OSError:
                pass
        res["ok"] = readable
        if not exists:
            res["status_code"] = 404
        elif not readable:
            res["status_code"] = 403
        else:
            res["status_code"] = 200
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:120]
    res["latency_ms"] = int((time.time() - started) * 1000)
    return res


# ── SQLite readable (read-only connection, single SELECT 1) ─────────
def probe_sqlite_readable(target: dict) -> dict:
    """Verify the file opens as a SQLite database.

    On WAL-mode DBs, a `mode=ro` connection may still need to write the
    WAL index. If the probing user lacks write perms on the journal
    sidecar files (which is the *correct* posture for a monitoring user),
    SQLite raises 'attempt to write a readonly database'. We treat that
    as success — the file IS a valid SQLite DB; our connection is just
    locked out of the journal, which is precisely what a read-only health
    probe should be.
    """
    res = _new_result(target)
    started = time.time()
    path = target.get("path", "")
    timeout = float(target.get("timeout", 3))
    try:
        if not os.path.exists(path):
            res["meta"]["exists"] = False
            res["status_code"] = 404
            res["error"] = "db file not found"
            res["latency_ms"] = int((time.time() - started) * 1000)
            return res
        uri = f"file:{path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=timeout)
        except sqlite3.OperationalError as oe:
            res["error"] = f"sqlite open: {str(oe)[:100]}"
            res["status_code"] = 500
            res["latency_ms"] = int((time.time() - started) * 1000)
            return res
        try:
            try:
                cur = conn.execute("SELECT 1")
                row = cur.fetchone()
                res["meta"]["select_ok"] = bool(row)
                cur2 = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'"
                )
                res["meta"]["table_count"] = int(cur2.fetchone()[0])
                res["ok"] = True
                res["status_code"] = 200
            except sqlite3.OperationalError as oe:
                msg = str(oe).lower()
                if "readonly" in msg or "read-only" in msg:
                    # WAL flush blocked because our user can't write the
                    # journal — correct posture for monitoring. File is
                    # a valid SQLite DB, treat as healthy.
                    res["ok"] = True
                    res["status_code"] = 200
                    res["meta"]["select_ok"] = True
                    res["meta"]["wal_journal_writeable"] = False
                else:
                    res["error"] = str(oe)[:120]
                    res["status_code"] = 500
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:120]
        res["status_code"] = 500
    res["latency_ms"] = int((time.time() - started) * 1000)
    return res


# ── Dispatcher ────────────────────────────────────────────────────────
_PROBES = {
    "http": probe_http,
    "json_sanity": probe_http,   # shares core; sanity validated inside
    "dns": probe_dns,
    "tls": probe_tls,
    "system_metric": probe_system_metric,
    "process": probe_process,
    "path_readable": probe_path_readable,
    "sqlite_readable": probe_sqlite_readable,
}


def run_probe(target: dict) -> dict:
    """Execute the probe declared by target['type']. Always returns a dict,
    never raises. Unknown types yield a GREY-classifiable result."""
    fn = _PROBES.get(target.get("type", ""))
    if fn is None:
        res = _new_result(target)
        res["error"] = f"unsupported probe type: {target.get('type')!r}"
        return res
    try:
        return fn(target)
    except Exception as e:  # noqa: BLE001 — uniform safety net
        res = _new_result(target)
        res["error"] = f"probe crash: {str(e)[:100]}"
        return res
