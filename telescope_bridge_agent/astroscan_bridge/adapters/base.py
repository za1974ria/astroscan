"""AstroScan Bridge — adapter contract (TB-3 prototype, READ-ONLY).

This module declares the ONLY public API surface that any concrete
adapter is allowed to expose:

    discover() -> list[DeviceDescriptor]
    read_device(device_local_id: str) -> TelemetrySample
    close() -> None

Subclasses MUST NOT add any other public method. The CI safety test
(`tests/test_safety_ast.py`) walks every .py in this package and refuses
identifiers that contain forbidden operation verbs (slew, park, goto,
move, pulse, sync, motor) outside the explicit predicate whitelist
(is_slewing, is_parked, is_moving, …).

The ASCOM/Alpaca property NAMES we accept are stored here as STRING
LITERALS (PascalCase). They are never used as Python attribute names in
this code — concrete adapters access them via getattr(obj, "<name>") or
HTTP path components, both of which are read-only operations by
construction.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ── Read-only property allow-lists per device kind ──────────────────
# These are STRINGS, never identifiers. Reading any property in this
# list via getattr() (ASCOM COM) or GET /api/v1/{type}/{n}/{prop}
# (Alpaca) is by construction a non-actuating observation.
TELESCOPE_READ_PROPERTIES: tuple[str, ...] = (
    "Name", "Description", "DriverInfo", "DriverVersion",
    "InterfaceVersion", "Connected",
    "RightAscension", "Declination", "Altitude", "Azimuth",
    "Tracking", "TrackingRate", "Slewing", "AtPark", "AtHome",
    "SideOfPier", "EquatorialSystem", "UTCDate",
    # The next three reveal the observatory location → opt-in only
    "SiteLatitude", "SiteLongitude", "SiteElevation",
)

CAMERA_READ_PROPERTIES: tuple[str, ...] = (
    "Name", "Description", "DriverInfo", "Connected",
    "CameraState", "CCDTemperature", "SetCCDTemperature",  # GET = target temp
    "CoolerOn", "CoolerPower", "BinX", "BinY",
    "Gain", "Offset", "PercentCompleted", "ImageReady",
)

FOCUSER_READ_PROPERTIES: tuple[str, ...] = (
    "Name", "Description", "Connected",
    "Position", "IsMoving", "MaxStep", "Temperature",
    "StepSize", "Absolute",
)

FILTERWHEEL_READ_PROPERTIES: tuple[str, ...] = (
    "Name", "Description", "Connected",
    "Position", "Names", "FocusOffsets",
)

READ_PROPERTIES_BY_KIND: dict[str, tuple[str, ...]] = {
    "mount":       TELESCOPE_READ_PROPERTIES,
    "camera":      CAMERA_READ_PROPERTIES,
    "focuser":     FOCUSER_READ_PROPERTIES,
    "filterwheel": FILTERWHEEL_READ_PROPERTIES,
}

# Alpaca path segment per kind (matches ASCOM device type strings).
ALPACA_KIND_TO_PATH: dict[str, str] = {
    "mount":       "telescope",
    "camera":      "camera",
    "focuser":     "focuser",
    "filterwheel": "filterwheel",
}


@dataclass(frozen=True)
class DeviceDescriptor:
    """Stable identity of a discovered device. Returned by discover()."""
    device_local_id: str           # e.g. "alpaca:telescope:0"
    kind: str                      # mount|camera|focuser|filterwheel
    name: str
    driver: str                    # alpaca|ascom_com|mock
    capabilities: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class TelemetrySample:
    """One read from one device. Matches docs/TELEMETRY_SCHEMA.md."""
    device_local_id: str
    kind: str
    ts_iso: str
    fields: dict   # validated, normalized payload (snake_case keys)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AbstractReadOnlyAdapter(ABC):
    """V1 contract — read-only, no actuation.

    Subclasses MUST NOT declare additional public methods. The CI test
    enforces this by introspecting each subclass's `__dict__`.
    """
    driver_name: str = "abstract"

    @abstractmethod
    def discover(self) -> list[DeviceDescriptor]:
        """Enumerate devices reachable by this adapter. Must NOT actuate."""

    @abstractmethod
    def read_device(self, device_local_id: str) -> TelemetrySample:
        """Read current telemetry. Property reads only."""

    def close(self) -> None:
        """Release resources. Default no-op. Must not affect hardware."""
        return None
