"""Mock adapter — synthetic data, no I/O, runs on any OS.

Used for development on Linux/macOS dev boxes and for CI. Never ships
enabled by default in production builds (selectable only via
`--driver mock` on the CLI)."""
from __future__ import annotations

import math
import time

from astroscan_bridge.adapters.base import (
    AbstractReadOnlyAdapter,
    DeviceDescriptor,
    TelemetrySample,
    now_iso,
)


class MockAdapter(AbstractReadOnlyAdapter):
    """Returns plausible synthetic telemetry for one mount, one camera,
    one focuser. Values drift smoothly so the dashboard charts look real."""

    driver_name = "mock"

    _DEVICES: tuple[DeviceDescriptor, ...] = (
        DeviceDescriptor(
            device_local_id="mock:telescope:0",
            kind="mount",
            name="Mock EQ6-R Pro",
            driver="mock",
            capabilities=("ra_dec", "tracking_state", "slewing_state"),
        ),
        DeviceDescriptor(
            device_local_id="mock:camera:0",
            kind="camera",
            name="Mock ASI2600MM",
            driver="mock",
            capabilities=("temperature", "exposure_state"),
        ),
        DeviceDescriptor(
            device_local_id="mock:focuser:0",
            kind="focuser",
            name="Mock ZWO EAF",
            driver="mock",
            capabilities=("position",),
        ),
    )

    def discover(self) -> list[DeviceDescriptor]:
        return list(self._DEVICES)

    def read_device(self, device_local_id: str) -> TelemetrySample:
        desc = next(
            (d for d in self._DEVICES if d.device_local_id == device_local_id),
            None,
        )
        if desc is None:
            raise KeyError(f"unknown device {device_local_id!r}")

        t = time.time()
        if desc.kind == "mount":
            fields = {
                "is_connected": True,
                "ra_hours": round((t / 3600.0) % 24.0, 5),
                "dec_degrees": round(20.0 * math.sin(t / 600.0), 3),
                "is_tracking": True,
                "tracking_rate": "sidereal",
                "is_slewing": False,
                "is_parked": False,
                "is_at_home": False,
                "side_of_pier": "east",
            }
        elif desc.kind == "camera":
            fields = {
                "is_connected": True,
                "is_exposing": False,
                "ccd_temp_c": round(-10.0 + math.sin(t / 100.0), 2),
                "ccd_target_temp_c": -10.0,
                "cooler_on": True,
                "cooler_power_pct": 67.0,
                "binning_x": 1,
                "binning_y": 1,
            }
        elif desc.kind == "focuser":
            fields = {
                "is_connected": True,
                "position": 15000 + int(50 * math.sin(t / 30.0)),
                "is_moving": False,
                "temp_c": 18.5,
                "max_step": 100000,
            }
        else:
            fields = {"is_connected": True}

        return TelemetrySample(
            device_local_id=device_local_id,
            kind=desc.kind,
            ts_iso=now_iso(),
            fields=fields,
        )
