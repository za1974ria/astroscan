"""TB-3.2 — Real Alpaca adapter, read-only validation.

No real network is touched: UDP discovery is bypassed via the
constructor `hosts=` argument; HTTP calls are intercepted by patching
`requests.Session.request` (the chokepoint that ReadOnlyHttpSession's
override delegates to).
"""
from __future__ import annotations

from typing import Any

import pytest

from astroscan_bridge.adapters.alpaca import (
    ALPACA_READ_FIELDS,
    AlpacaAdapter,
    _normalize_camera,
    _normalize_filterwheel,
    _normalize_focuser,
    _normalize_mount,
    _parse_device_local_id,
)
from astroscan_bridge.adapters.base import (
    READ_PROPERTIES_BY_KIND,
    DeviceDescriptor,
    TelemetrySample,
)
from astroscan_bridge.safety.http_guard import ReadOnlyHttpSession
from astroscan_bridge.safety.readonly_filter import WriteAttemptError


# ── Helpers ──────────────────────────────────────────────────────────
class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if not 200 <= self.status_code < 300:
            raise RuntimeError(f"HTTP {self.status_code}")


def _envelope(value: Any, error_number: int = 0,
              error_message: str = "") -> dict:
    return {
        "Value": value,
        "ClientTransactionID": 1,
        "ServerTransactionID": 1,
        "ErrorNumber": error_number,
        "ErrorMessage": error_message,
    }


def _install_router(monkeypatch, routes: dict[str, Any]):
    """Install a fake `requests.Session.request` that dispatches by
    substring matching the URL against `routes` keys."""
    captured: list[tuple[str, str]] = []

    def fake_request(self, method, url, *args, **kwargs):
        captured.append((method, url))
        for needle, factory in routes.items():
            if needle in url:
                resp = factory(url) if callable(factory) else factory
                return resp
        raise AssertionError(f"unexpected URL: {method} {url}")

    monkeypatch.setattr("requests.Session.request", fake_request)
    return captured


# ── 1. ReadOnlyHttpSession guard ─────────────────────────────────────
@pytest.mark.parametrize("method", ["put", "post", "delete", "patch"])
def test_session_blocks_convenience_write_methods(method):
    session = ReadOnlyHttpSession()
    fn = getattr(session, method)
    with pytest.raises(WriteAttemptError):
        fn("http://example.invalid/")


@pytest.mark.parametrize("method", ["PUT", "POST", "DELETE", "PATCH",
                                     "OPTIONS", "TRACE", "CONNECT",
                                     "put", "post", "DeLeTe"])
def test_session_blocks_low_level_request_with_write_method(method):
    session = ReadOnlyHttpSession()
    with pytest.raises(WriteAttemptError):
        session.request(method, "http://example.invalid/")


def test_session_allows_get(monkeypatch):
    """GET must reach the parent Session.request unchanged."""
    seen: dict = {}

    def fake_parent_request(self, method, url, *args, **kwargs):
        seen["method"] = method
        seen["url"] = url
        return _FakeResponse(_envelope(True))

    monkeypatch.setattr("requests.Session.request", fake_parent_request)
    session = ReadOnlyHttpSession()
    resp = session.get("http://example.invalid/probe")
    assert seen == {"method": "GET", "url": "http://example.invalid/probe"}
    assert resp.json()["Value"] is True


def test_session_allows_head(monkeypatch):
    seen: dict = {}

    def fake_parent_request(self, method, url, *args, **kwargs):
        seen["method"] = method
        return _FakeResponse({})

    monkeypatch.setattr("requests.Session.request", fake_parent_request)
    session = ReadOnlyHttpSession()
    session.head("http://example.invalid/")
    assert seen["method"] == "HEAD"


# ── 2. device_local_id round-trip ────────────────────────────────────
def test_parse_device_local_id():
    type_path, n, host, port = _parse_device_local_id(
        "alpaca:telescope:0@192.168.1.10:11111"
    )
    assert (type_path, n, host, port) == ("telescope", 0, "192.168.1.10", 11111)


@pytest.mark.parametrize("bad", [
    "wat:not-an-alpaca-id",
    "alpaca:telescope:0",          # missing @host:port
    "alpaca:telescope:notanint@h:1",  # bad number
    "alpaca:telescope:0@host_no_port",
])
def test_parse_device_local_id_rejects_malformed(bad):
    with pytest.raises(ValueError):
        _parse_device_local_id(bad)


# ── 3. Discovery parsing ─────────────────────────────────────────────
def test_discover_filters_to_supported_kinds_only(monkeypatch):
    routes = {
        "/management/v1/configureddevices": _FakeResponse(_envelope([
            {"DeviceType": "Telescope",   "DeviceNumber": 0,
             "DeviceName": "EQ6-R Pro",   "UniqueID": "u1"},
            {"DeviceType": "Camera",      "DeviceNumber": 0,
             "DeviceName": "ASI2600MM",   "UniqueID": "u2"},
            {"DeviceType": "Focuser",     "DeviceNumber": 0,
             "DeviceName": "ZWO EAF",     "UniqueID": "u3"},
            {"DeviceType": "FilterWheel", "DeviceNumber": 0,
             "DeviceName": "ZWO EFW",     "UniqueID": "u4"},
            # Unsupported kinds — must be filtered out.
            {"DeviceType": "Dome",        "DeviceNumber": 0,
             "DeviceName": "MyDome",      "UniqueID": "u5"},
            {"DeviceType": "Rotator",     "DeviceNumber": 0,
             "DeviceName": "MyRotator",   "UniqueID": "u6"},
        ])),
    }
    _install_router(monkeypatch, routes)

    adapter = AlpacaAdapter(hosts=[("127.0.0.1", 11111)])
    devs = adapter.discover()
    kinds = sorted(d.kind for d in devs)
    assert kinds == ["camera", "filterwheel", "focuser", "mount"]
    assert all(isinstance(d, DeviceDescriptor) for d in devs)
    mount = next(d for d in devs if d.kind == "mount")
    assert mount.name == "EQ6-R Pro"
    assert mount.driver == "alpaca"
    assert mount.device_local_id == "alpaca:telescope:0@127.0.0.1:11111"


def test_discover_skips_servers_with_alpaca_error(monkeypatch):
    routes = {
        "/management/v1/configureddevices": _FakeResponse(_envelope(
            None, error_number=999, error_message="server broken")),
    }
    _install_router(monkeypatch, routes)
    adapter = AlpacaAdapter(hosts=[("127.0.0.1", 11111)])
    assert adapter.discover() == []


def test_discover_with_empty_hosts_returns_empty(monkeypatch):
    # No URL should ever be requested.
    captured = _install_router(monkeypatch, {})
    adapter = AlpacaAdapter(hosts=[])
    assert adapter.discover() == []
    assert captured == []


# ── 4. Telemetry parsing — minimal field set per spec ────────────────
def _telescope_router(values: dict[str, Any]) -> dict[str, Any]:
    """Build a router with mgmt + telescope property responses."""
    def factory_for_property(url: str) -> _FakeResponse:
        prop = url.split("/api/v1/telescope/0/")[1].split("?")[0]
        return _FakeResponse(_envelope(values[prop]))

    return {
        "/management/v1/configureddevices": _FakeResponse(_envelope([
            {"DeviceType": "Telescope", "DeviceNumber": 0,
             "DeviceName": "EQ6", "UniqueID": "u1"},
        ])),
        "/api/v1/telescope/0/": factory_for_property,
    }


def test_mount_telemetry_minimal_fields_only(monkeypatch):
    captured = _install_router(monkeypatch, _telescope_router({
        "rightascension": 5.123,
        "declination": 12.345,
        "tracking": True,
        "connected": True,
    }))

    adapter = AlpacaAdapter(hosts=[("127.0.0.1", 11111)])
    devs = adapter.discover()
    sample = adapter.read_device(devs[0].device_local_id)

    assert isinstance(sample, TelemetrySample)
    assert sample.kind == "mount"
    assert sample.fields == {
        "is_connected": True,
        "ra_hours": 5.123,
        "dec_degrees": 12.345,
        "is_tracking": True,
    }
    # Verify EXACTLY the 4 spec'd properties were fetched (no more, no less).
    prop_urls = [u for (_m, u) in captured if "/api/v1/telescope/0/" in u]
    fetched = sorted(u.split("/api/v1/telescope/0/")[1].split("?")[0]
                     for u in prop_urls)
    assert fetched == ["connected", "declination", "rightascension", "tracking"]
    # Every HTTP method was GET.
    assert all(m == "GET" for (m, _u) in captured)


def test_camera_telemetry_minimal_fields_only(monkeypatch):
    def routes_factory(url: str) -> _FakeResponse:
        prop = url.split("/api/v1/camera/0/")[1].split("?")[0]
        return _FakeResponse(_envelope({
            "connected": True,
            "ccdtemperature": -10.5,
            "cooleron": True,
        }[prop]))

    _install_router(monkeypatch, {
        "/management/v1/configureddevices": _FakeResponse(_envelope([
            {"DeviceType": "Camera", "DeviceNumber": 0,
             "DeviceName": "ASI", "UniqueID": "x"},
        ])),
        "/api/v1/camera/0/": routes_factory,
    })

    adapter = AlpacaAdapter(hosts=[("127.0.0.1", 11111)])
    devs = adapter.discover()
    sample = adapter.read_device(devs[0].device_local_id)
    assert sample.fields == {
        "is_connected": True,
        "ccd_temp_c": -10.5,
        "cooler_on": True,
    }


def test_focuser_telemetry_minimal_fields_only(monkeypatch):
    def routes_factory(url: str) -> _FakeResponse:
        prop = url.split("/api/v1/focuser/0/")[1].split("?")[0]
        return _FakeResponse(_envelope({
            "connected": True,
            "position": 15000,
            "temperature": 18.5,
        }[prop]))

    _install_router(monkeypatch, {
        "/management/v1/configureddevices": _FakeResponse(_envelope([
            {"DeviceType": "Focuser", "DeviceNumber": 0,
             "DeviceName": "EAF", "UniqueID": "f"},
        ])),
        "/api/v1/focuser/0/": routes_factory,
    })

    adapter = AlpacaAdapter(hosts=[("127.0.0.1", 11111)])
    devs = adapter.discover()
    sample = adapter.read_device(devs[0].device_local_id)
    assert sample.fields == {
        "is_connected": True,
        "position": 15000,
        "temp_c": 18.5,
    }


def test_alpaca_property_error_is_recorded(monkeypatch):
    def routes_factory(url: str) -> _FakeResponse:
        # Every property returns an Alpaca error.
        return _FakeResponse(_envelope(
            None, error_number=1024, error_message="NotConnected"))

    _install_router(monkeypatch, {
        "/management/v1/configureddevices": _FakeResponse(_envelope([
            {"DeviceType": "Telescope", "DeviceNumber": 0,
             "DeviceName": "EQ6", "UniqueID": "x"},
        ])),
        "/api/v1/telescope/0/": routes_factory,
    })

    adapter = AlpacaAdapter(hosts=[("127.0.0.1", 11111)])
    devs = adapter.discover()
    sample = adapter.read_device(devs[0].device_local_id)
    assert sample.fields["is_connected"] is False  # None -> bool() -> False
    assert sample.fields["ra_hours"] is None
    assert "_alpaca_errors" in sample.fields
    assert all("NotConnected" in e for e in sample.fields["_alpaca_errors"])


def test_unknown_device_id_raises():
    adapter = AlpacaAdapter(hosts=[])
    with pytest.raises(KeyError):
        adapter.read_device("alpaca:telescope:99@1.2.3.4:5678")


# ── 5. Allow-list enforcement (defensive cross-check) ────────────────
def test_alpaca_read_fields_are_subset_of_safety_allowlist():
    """The TB-3.2 minimal read set must be a subset of the maximal
    safety allow-list declared in adapters/base.py."""
    for kind, props in ALPACA_READ_FIELDS.items():
        max_allowed = set(READ_PROPERTIES_BY_KIND[kind])
        assert set(props) <= max_allowed, (
            f"kind={kind}: TB-3.2 reads {set(props) - max_allowed} "
            f"which are not in the safety allow-list."
        )


# ── 6. Normaliser sanity ─────────────────────────────────────────────
def test_normalizers_handle_missing_keys():
    assert _normalize_mount({}) == {
        "is_connected": False, "ra_hours": None,
        "dec_degrees": None, "is_tracking": None,
    }
    assert _normalize_camera({}) == {
        "is_connected": False, "ccd_temp_c": None, "cooler_on": None,
    }
    assert _normalize_focuser({}) == {
        "is_connected": False, "position": None, "temp_c": None,
    }
    assert _normalize_filterwheel({}) == {
        "is_connected": False, "current_slot": None, "filter_names": None,
    }
