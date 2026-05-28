"""Alpaca adapter — ASCOM Alpaca over HTTP, read-only (TB-3.2).

Two operations only:

  1. discover()
       - sends UDP broadcast `alpacadiscovery1` on port 32227 (or uses
         hosts injected via the constructor — useful for tests).
       - for each responding server, HTTP GET
         /management/v1/configureddevices
       - returns DeviceDescriptors for supported device kinds:
         mount, camera, focuser, filterwheel.

  2. read_device(device_local_id)
       - for each property in the minimal per-kind read set
         (see ALPACA_READ_FIELDS), HTTP GET
         /api/v1/{type}/{n}/{property}
       - normalises Alpaca camelCase response into our snake_case
         telemetry schema.

Safety layers, in order of evaluation:

  A. The HTTP transport is `ReadOnlyHttpSession`, which raises
     `WriteAttemptError` on every non-GET/HEAD method BEFORE any network
     call. No code path in this file invokes PUT, POST, PATCH, DELETE
     (verified by AST scan and `tests/test_alpaca_readonly.py`).
  B. Every property read passes through
     `safety.readonly_filter.enforce_property_allowlist(kind, prop)`
     which refuses property names that are not in the per-kind allow
     list declared in `adapters/base.py`.
  C. Alpaca error responses (ErrorNumber != 0) are surfaced as
     per-field `None` plus a `_alpaca_errors` accumulator so the caller
     can distinguish a value of None from an upstream error.

This module imports nothing that could perform a write to telescope
hardware. Property names are PascalCase string LITERALS, never Python
attributes — so the AST safety scan does not flag them.
"""
from __future__ import annotations

import json
import socket
from typing import Any

from astroscan_bridge.adapters.base import (
    ALPACA_KIND_TO_PATH,
    AbstractReadOnlyAdapter,
    DeviceDescriptor,
    TelemetrySample,
    now_iso,
)
from astroscan_bridge.safety.http_guard import ReadOnlyHttpSession
from astroscan_bridge.safety.readonly_filter import enforce_property_allowlist


# ── Discovery constants ──────────────────────────────────────────────
_DISCOVERY_PAYLOAD = b"alpacadiscovery1"
_DISCOVERY_PORT = 32227
_HTTP_TIMEOUT = 4.0
_CLIENT_ID = 1
_TRANSACTION_ID = 1

# ASCOM Alpaca DeviceType (PascalCase) -> our internal `kind`.
_TYPE_TO_KIND: dict[str, str] = {
    "Telescope":   "mount",
    "Camera":      "camera",
    "Focuser":     "focuser",
    "FilterWheel": "filterwheel",
}

# Per-kind subset of properties the Alpaca adapter actually reads in
# TB-3.2. This is a SUBSET of READ_PROPERTIES_BY_KIND (the maximal
# safety allow-list). enforce_property_allowlist() is called for every
# entry below as a defensive cross-check.
ALPACA_READ_FIELDS: dict[str, tuple[str, ...]] = {
    "mount":       ("RightAscension", "Declination", "Tracking", "Connected"),
    "camera":      ("Connected", "CCDTemperature", "CoolerOn"),
    "focuser":     ("Connected", "Position", "Temperature"),
    "filterwheel": ("Connected", "Position", "Names"),
}


# ── UDP discovery (skipped when hosts are injected) ──────────────────
def _discover_servers_udp(timeout: float) -> list[tuple[str, int]]:
    """Broadcast UDP discovery on the LAN. Returns (host, port) tuples.

    No telescope is contacted by this function — it only locates Alpaca
    HTTP servers."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    servers: list[tuple[str, int]] = []
    try:
        sock.sendto(_DISCOVERY_PAYLOAD, ("255.255.255.255", _DISCOVERY_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                break
            try:
                payload = json.loads(data.decode("utf-8"))
                port = int(payload.get("AlpacaPort", 11111))
                servers.append((addr[0], port))
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                continue
    finally:
        sock.close()
    return servers


# ── device_local_id parser ───────────────────────────────────────────
def _parse_device_local_id(device_local_id: str) -> tuple[str, int, str, int]:
    """Round-trip `alpaca:<type_path>:<n>@<host>:<port>` -> components.

    Raises ValueError if the string is malformed."""
    if not device_local_id.startswith("alpaca:"):
        raise ValueError(f"not an Alpaca device id: {device_local_id!r}")
    body = device_local_id[len("alpaca:"):]
    try:
        type_n, hostport = body.split("@", 1)
        type_path, n_str = type_n.split(":", 1)
        host, port_str = hostport.rsplit(":", 1)
        return type_path, int(n_str), host, int(port_str)
    except ValueError as e:
        raise ValueError(
            f"malformed Alpaca device id: {device_local_id!r}"
        ) from e


# ── Per-kind normalisers (Alpaca PascalCase -> snake_case fields) ────
def _normalize_mount(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_connected": bool(raw.get("Connected", False)),
        "ra_hours": raw.get("RightAscension"),
        "dec_degrees": raw.get("Declination"),
        "is_tracking": raw.get("Tracking"),
    }


def _normalize_camera(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_connected": bool(raw.get("Connected", False)),
        "ccd_temp_c": raw.get("CCDTemperature"),
        "cooler_on": raw.get("CoolerOn"),
    }


def _normalize_focuser(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_connected": bool(raw.get("Connected", False)),
        "position": raw.get("Position"),
        "temp_c": raw.get("Temperature"),
    }


def _normalize_filterwheel(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_connected": bool(raw.get("Connected", False)),
        "current_slot": raw.get("Position"),
        "filter_names": raw.get("Names"),
    }


_NORMALIZERS: dict[str, Any] = {
    "mount":       _normalize_mount,
    "camera":      _normalize_camera,
    "focuser":     _normalize_focuser,
    "filterwheel": _normalize_filterwheel,
}


# ── Adapter ──────────────────────────────────────────────────────────
class AlpacaAdapter(AbstractReadOnlyAdapter):
    driver_name = "alpaca"

    def __init__(
        self,
        hosts: list[tuple[str, int]] | None = None,
        discovery_timeout: float = 2.0,
    ) -> None:
        """If `hosts` is provided, UDP discovery is skipped and those
        addresses are queried directly. `hosts=[]` disables discovery
        entirely (useful for negative tests)."""
        self._hosts_override = hosts
        self._discovery_timeout = discovery_timeout
        # device_local_id -> (host, port, type_path, device_number, kind, name)
        self._devices: dict[str, tuple] = {}
        self._session = ReadOnlyHttpSession()
        self._session.headers.update(
            {"User-Agent": "AstroScan-Bridge/0.3.2-tb3.2"}
        )

    # ── private helpers ──────────────────────────────────────────────
    def _hosts(self) -> list[tuple[str, int]]:
        if self._hosts_override is not None:
            return list(self._hosts_override)
        return _discover_servers_udp(self._discovery_timeout)

    def _http_get_json(self, url: str) -> dict[str, Any]:
        """Single chokepoint for outbound HTTP. Always returns a dict
        (the Alpaca envelope). Network errors propagate."""
        resp = self._session.get(
            url,
            params={
                "ClientID": _CLIENT_ID,
                "ClientTransactionID": _TRANSACTION_ID,
            },
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"unexpected Alpaca response shape from {url}")
        return data

    # ── public contract ──────────────────────────────────────────────
    def discover(self) -> list[DeviceDescriptor]:
        descriptors: list[DeviceDescriptor] = []
        self._devices.clear()
        for host, port in self._hosts():
            url = f"http://{host}:{port}/management/v1/configureddevices"
            try:
                payload = self._http_get_json(url)
            except Exception:
                # An unreachable Alpaca server must not abort whole discovery.
                continue
            if payload.get("ErrorNumber"):
                continue
            entries = payload.get("Value") or []
            for entry in entries:
                device_type = entry.get("DeviceType", "")
                kind = _TYPE_TO_KIND.get(device_type)
                if kind is None:
                    continue
                n = int(entry.get("DeviceNumber", 0))
                name = entry.get("DeviceName", f"{device_type}#{n}")
                type_path = ALPACA_KIND_TO_PATH[kind]
                device_local_id = f"alpaca:{type_path}:{n}@{host}:{port}"
                self._devices[device_local_id] = (
                    host, port, type_path, n, kind, name,
                )
                descriptors.append(DeviceDescriptor(
                    device_local_id=device_local_id,
                    kind=kind,
                    name=name,
                    driver=self.driver_name,
                    capabilities=ALPACA_READ_FIELDS.get(kind, ()),
                ))
        return descriptors

    def read_device(self, device_local_id: str) -> TelemetrySample:
        if device_local_id not in self._devices:
            self.discover()
        if device_local_id not in self._devices:
            raise KeyError(f"unknown device {device_local_id!r}")

        host, port, type_path, n, kind, _name = self._devices[device_local_id]
        properties = ALPACA_READ_FIELDS.get(kind, ())
        fields_raw: dict[str, Any] = {}
        errors: list[str] = []

        for prop in properties:
            # Final defensive cross-check against the per-kind allow-list
            # declared in adapters/base.py — refuses anything outside it.
            enforce_property_allowlist(kind, prop)
            url = f"http://{host}:{port}/api/v1/{type_path}/{n}/{prop.lower()}"
            try:
                payload = self._http_get_json(url)
            except Exception as exc:
                errors.append(f"{prop}: {exc.__class__.__name__}")
                fields_raw[prop] = None
                continue
            if payload.get("ErrorNumber"):
                errors.append(
                    f"{prop}: Alpaca[{payload.get('ErrorNumber')}]"
                    f" {payload.get('ErrorMessage','')}"
                )
                fields_raw[prop] = None
            else:
                fields_raw[prop] = payload.get("Value")

        normalize = _NORMALIZERS[kind]
        normalized = normalize(fields_raw)
        if errors:
            normalized["_alpaca_errors"] = errors

        return TelemetrySample(
            device_local_id=device_local_id,
            kind=kind,
            ts_iso=now_iso(),
            fields=normalized,
        )

    def close(self) -> None:
        self._devices.clear()
        try:
            self._session.close()
        except Exception:
            pass
