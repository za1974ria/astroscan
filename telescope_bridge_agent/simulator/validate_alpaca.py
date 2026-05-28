"""TB-3.2.1 deterministic validation against local Alpaca simulator.

Bypasses UDP discovery by passing hosts=["http://127.0.0.1:11111"] explicitly,
then exercises discover() + read_device() for every reported device.
Exit code 0 = success, 1 = failure.
"""
from __future__ import annotations

import json
import sys

from astroscan_bridge.adapters.alpaca import AlpacaAdapter

SIM_HOST = "http://127.0.0.1:11111"
EXPECTED_KINDS = {"mount", "camera", "focuser"}


def main() -> int:
    adapter = AlpacaAdapter(hosts=[SIM_HOST], timeout_s=2.0)
    try:
        devices = adapter.discover()
        print("== DISCOVER ==")
        print(json.dumps([d.to_dict() for d in devices], indent=2))

        if not devices:
            print("FAIL: discover() returned no devices", file=sys.stderr)
            return 1

        kinds_seen = {d.kind for d in devices}
        missing = EXPECTED_KINDS - kinds_seen
        if missing:
            print(f"FAIL: missing device kinds: {sorted(missing)}", file=sys.stderr)
            return 1

        print("== TELEMETRY ==")
        for d in devices:
            sample = adapter.read_device(d.device_local_id)
            print(json.dumps(sample.to_dict(), indent=2))
            if not sample.fields.get("is_connected"):
                print(f"FAIL: device {d.device_local_id} reported is_connected=False", file=sys.stderr)
                return 1

        print("== OK ==")
        return 0
    finally:
        adapter.close()


if __name__ == "__main__":
    sys.exit(main())
