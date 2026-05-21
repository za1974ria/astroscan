"""Unit tests — guardian.collectors (mocks subprocess / urllib / fs)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.blueprints.guardian import collectors

pytestmark = pytest.mark.unit


# ─── envelope shape ─────────────────────────────────────────────────────────


def test_envelope_required_fields():
    env = collectors._envelope("x", True, value={"a": 1}, severity="warn", latency_ms=12)
    assert env["name"] == "x"
    assert env["ok"] is True
    assert env["value"] == {"a": 1}
    assert env["severity"] == "warn"
    assert "ts" in env
    assert env["latency_ms"] == 12


# ─── _safe_subprocess ───────────────────────────────────────────────────────


def test_safe_subprocess_invalid_args():
    ok, out, err = collectors._safe_subprocess([])
    assert ok is False
    assert err == "invalid_args"


def test_safe_subprocess_rejects_shell_str():
    ok, out, err = collectors._safe_subprocess("ls -la")  # type: ignore[arg-type]
    assert ok is False
    assert err == "invalid_args"


def test_safe_subprocess_binary_not_found():
    ok, out, err = collectors._safe_subprocess(["/nonexistent/binary/xxx"])
    assert ok is False
    assert err == "binary_not_found"


def test_safe_subprocess_real_echo():
    ok, out, err = collectors._safe_subprocess(["echo", "hello"])
    assert ok is True
    assert "hello" in out


# ─── systemd_astroscan ──────────────────────────────────────────────────────


def test_systemd_astroscan_active(monkeypatch):
    monkeypatch.setattr(collectors, "_safe_subprocess", lambda *a, **kw: (True, "active\n", ""))
    r = collectors.collect_systemd_astroscan()
    assert r["name"] == "systemd_astroscan"
    assert r["value"]["active"] is True
    assert r["severity"] == "info"


def test_systemd_astroscan_inactive(monkeypatch):
    monkeypatch.setattr(collectors, "_safe_subprocess", lambda *a, **kw: (False, "inactive\n", ""))
    r = collectors.collect_systemd_astroscan()
    assert r["value"]["active"] is False
    assert r["severity"] == "critical"


# ─── http probes ────────────────────────────────────────────────────────────


def test_http_root_ok(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.__enter__ = lambda s: fake_resp
    fake_resp.__exit__ = lambda *a: None
    fake_resp.status = 200
    monkeypatch.setattr(
        "app.blueprints.guardian.collectors.urllib_request.urlopen", lambda *a, **kw: fake_resp
    )
    r = collectors.collect_http_root()
    assert r["ok"] is True
    assert r["value"]["status"] == 200
    assert r["severity"] == "info"


def test_http_root_500_critical(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.__enter__ = lambda s: fake_resp
    fake_resp.__exit__ = lambda *a: None
    fake_resp.status = 503
    monkeypatch.setattr(
        "app.blueprints.guardian.collectors.urllib_request.urlopen", lambda *a, **kw: fake_resp
    )
    r = collectors.collect_http_root()
    assert r["severity"] == "critical"


def test_http_root_connection_refused(monkeypatch):
    def boom(*a, **kw):
        raise ConnectionRefusedError("nope")

    monkeypatch.setattr("app.blueprints.guardian.collectors.urllib_request.urlopen", boom)
    r = collectors.collect_http_root()
    assert r["ok"] is False
    assert r["severity"] == "critical"


# ─── disk ───────────────────────────────────────────────────────────────────


def test_disk_normal(monkeypatch):
    out = "Filesystem     1024-blocks   Used Available Capacity Mounted on\n/dev/sda1   10000000 2500000  7500000      25% /\n"
    monkeypatch.setattr(collectors, "_safe_subprocess", lambda *a, **kw: (True, out, ""))
    r = collectors.collect_disk()
    assert r["ok"] is True
    assert r["value"]["percent_used"] == 25
    assert r["severity"] == "info"


def test_disk_warn(monkeypatch):
    out = "F  B U Av Cap M\n/x 1 1 1 85% /\n"
    monkeypatch.setattr(collectors, "_safe_subprocess", lambda *a, **kw: (True, out, ""))
    r = collectors.collect_disk()
    assert r["severity"] == "warn"
    assert r["value"]["percent_used"] == 85


def test_disk_critical(monkeypatch):
    out = "F  B U Av Cap M\n/x 1 1 1 95% /\n"
    monkeypatch.setattr(collectors, "_safe_subprocess", lambda *a, **kw: (True, out, ""))
    r = collectors.collect_disk()
    assert r["severity"] == "critical"


def test_disk_subprocess_failed(monkeypatch):
    monkeypatch.setattr(
        collectors, "_safe_subprocess", lambda *a, **kw: (False, "", "binary_not_found")
    )
    r = collectors.collect_disk()
    assert r["ok"] is False


# ─── ram ────────────────────────────────────────────────────────────────────


def test_ram_normal(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:    16000000 kB\nMemAvailable: 12000000 kB\n")
    r = collectors.collect_ram(meminfo_path=str(meminfo))
    assert r["ok"] is True
    assert 24.5 <= r["value"]["percent_used"] <= 25.5
    assert r["severity"] == "info"


def test_ram_critical(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:    100 kB\nMemAvailable: 5 kB\n")
    r = collectors.collect_ram(meminfo_path=str(meminfo))
    assert r["severity"] == "critical"


def test_ram_missing_file():
    r = collectors.collect_ram(meminfo_path="/no/such/file")
    assert r["ok"] is False


# ─── cpu_load ───────────────────────────────────────────────────────────────


def test_cpu_load_normal(tmp_path):
    p = tmp_path / "loadavg"
    p.write_text("0.50 0.40 0.30 1/100 12345\n")
    r = collectors.collect_cpu_load(loadavg_path=str(p))
    assert r["ok"] is True
    assert r["value"]["load_5m"] == 0.4
    assert r["severity"] == "info"


def test_cpu_load_critical(tmp_path):
    p = tmp_path / "loadavg"
    p.write_text("9.0 9.5 10.0 1/1 1\n")
    r = collectors.collect_cpu_load(loadavg_path=str(p))
    assert r["severity"] == "critical"


def test_cpu_load_missing_file():
    r = collectors.collect_cpu_load(loadavg_path="/nope/loadavg")
    assert r["ok"] is False


# ─── nginx ──────────────────────────────────────────────────────────────────


def test_nginx_active(monkeypatch):
    monkeypatch.setattr(collectors, "_safe_subprocess", lambda *a, **kw: (True, "active\n", ""))
    r = collectors.collect_nginx()
    assert r["value"]["active"] is True
    assert r["severity"] == "info"


def test_nginx_inactive(monkeypatch):
    monkeypatch.setattr(collectors, "_safe_subprocess", lambda *a, **kw: (False, "inactive\n", ""))
    r = collectors.collect_nginx()
    assert r["value"]["active"] is False
    assert r["severity"] == "critical"


# ─── log_anomalies ──────────────────────────────────────────────────────────


def test_log_anomalies_clean(tmp_path):
    p = tmp_path / "log.log"
    p.write_text("INFO ok\nINFO ok\nINFO ok\n")
    r = collectors.collect_log_anomalies(log_file=str(p))
    assert r["ok"] is True
    assert r["value"]["error_count"] == 0


def test_log_anomalies_with_errors(tmp_path):
    p = tmp_path / "log.log"
    p.write_text("\n".join(["ERROR boom"] * 60 + ["CRITICAL crash"] + ["INFO ok"] * 10))
    r = collectors.collect_log_anomalies(log_file=str(p))
    assert r["ok"] is True
    assert r["value"]["error_count"] >= 50
    assert r["value"]["critical_count"] >= 1
    assert r["severity"] == "warn"


def test_log_anomalies_absent_file_is_info(tmp_path):
    r = collectors.collect_log_anomalies(log_file=str(tmp_path / "absent.log"))
    assert r["ok"] is True
    assert r["value"]["note"] == "file_absent"
    assert r["severity"] == "info"


# ─── freshness ──────────────────────────────────────────────────────────────


def test_iss_feed_freshness_no_file(monkeypatch, tmp_path):
    r = collectors.collect_iss_feed_freshness(custom_path=str(tmp_path / "absent.json"))
    # Fallback path checks PROJECT_ROOT files; here we only check no-file flow
    assert r["ok"] is True


def test_weather_freshness_with_fresh_file(tmp_path):
    p = tmp_path / "w.json"
    p.write_text('{"x":1}')
    r = collectors.collect_weather_freshness(custom_path=str(p))
    assert r["ok"] is True
    assert r["value"]["age_seconds"] is not None
    assert r["value"]["age_seconds"] >= 0


# ─── collect_all ────────────────────────────────────────────────────────────


def test_collect_all_returns_list_of_envelopes(monkeypatch):
    # Stub each collector to return a tiny dict so we don't touch the system
    for c in collectors.ALL_COLLECTORS:
        monkeypatch.setattr(
            collectors, c.__name__, lambda _c=c: collectors._envelope(_c.__name__, True)
        )
    out = collectors.collect_all()
    assert isinstance(out, list)
    # Each entry has the required shape
    for e in out:
        assert "name" in e
        assert "ok" in e
        assert "severity" in e


def test_collect_all_crashed_collector_is_caught(monkeypatch):
    def bad():
        raise RuntimeError("kaboom")

    # Inject a bad collector into ALL_COLLECTORS for this test
    monkeypatch.setattr(collectors, "ALL_COLLECTORS", [bad])
    out = collectors.collect_all()
    assert len(out) == 1
    assert out[0]["ok"] is False
    assert "collector_crashed" in out[0].get("error", "")
