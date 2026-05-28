"""Continuous polling loop. Local stdout output only — no cloud upload
in TB-3. Ctrl-C exits cleanly."""
from __future__ import annotations

import json
import signal
import time

from astroscan_bridge.adapters.base import AbstractReadOnlyAdapter
from astroscan_bridge.safety.audit import audit


_stop = False


def _handle_sigint(signum, frame):
    global _stop
    _stop = True


def poll_loop(adapter: AbstractReadOnlyAdapter, *,
              interval_s: int = 5,
              max_iterations: int | None = None) -> None:
    """Continuously discover + read all devices.

    Args:
        adapter: any concrete read-only adapter.
        interval_s: seconds between cycles.
        max_iterations: optional cap (useful for tests).
    """
    signal.signal(signal.SIGINT, _handle_sigint)
    audit("poll_start", driver=adapter.driver_name, interval_s=interval_s)

    iteration = 0
    devices = adapter.discover()
    audit("poll_devices", driver=adapter.driver_name,
          count=len(devices),
          ids=[d.device_local_id for d in devices])

    while not _stop:
        iteration += 1
        cycle_started = time.time()
        cycle_samples = []
        for dev in devices:
            try:
                sample = adapter.read_device(dev.device_local_id)
                cycle_samples.append({
                    "device_local_id": sample.device_local_id,
                    "kind": sample.kind,
                    "ts": sample.ts_iso,
                    "fields": sample.fields,
                })
            except Exception as exc:  # noqa: BLE001
                audit("poll_read_error",
                      driver=adapter.driver_name,
                      device=dev.device_local_id,
                      error=str(exc)[:200])
        print(json.dumps({
            "iteration": iteration,
            "samples": cycle_samples,
            "elapsed_ms": int((time.time() - cycle_started) * 1000),
        }, default=str), flush=True)

        if max_iterations is not None and iteration >= max_iterations:
            break

        # Sleep but stay responsive to SIGINT.
        for _ in range(interval_s):
            if _stop:
                break
            time.sleep(1)

    audit("poll_stop", driver=adapter.driver_name, iterations=iteration)
    adapter.close()
