"""AstroScan Bridge Agent — CLI entrypoint (TB-3.2 + TB-35).

Supported drivers in this build:
  - mock   : synthetic data, runs on any OS (TB-3.1)
  - alpaca : real Alpaca discovery + telemetry, read-only (TB-3.2)

ASCOM COM (Windows native) arrives in TB-3.3.

TB-35 adds autonomous cloud transmission via `cloud-pair` and
`cloud-run`. These only POST to the operator-supplied AstroScan
cloud base URL; the telescope hardware is still read-only.

Usage:
    python -m astroscan_bridge --driver mock   discover
    python -m astroscan_bridge --driver alpaca discover
    python -m astroscan_bridge --driver alpaca telemetry --device-id <id>
    python -m astroscan_bridge --driver alpaca poll --interval 5
    python -m astroscan_bridge --driver alpaca cloud-pair \\
        --base-url http://127.0.0.1:5003/api/telescope-bridge \\
        --agent-id bridge-local-001
    python -m astroscan_bridge --driver alpaca cloud-run \\
        --base-url http://127.0.0.1:5003/api/telescope-bridge \\
        --agent-id bridge-local-001 --interval 10

V1 is READ-ONLY for telescope hardware. No motion commands ever.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from astroscan_bridge.adapters.base import AbstractReadOnlyAdapter
from astroscan_bridge.adapters.mock import MockAdapter
from astroscan_bridge.safety.audit import audit


def _load_adapter(name: str) -> AbstractReadOnlyAdapter:
    if name == "mock":
        return MockAdapter()
    if name == "alpaca":
        from astroscan_bridge.adapters.alpaca import AlpacaAdapter
        return AlpacaAdapter()
    raise ValueError(
        f"unknown driver: {name!r}. TB-3.2 supports 'mock' and 'alpaca'. "
        f"ASCOM COM arrives in TB-3.3."
    )


def _cmd_discover(args) -> int:
    adapter = _load_adapter(args.driver)
    descriptors = adapter.discover()
    audit("cli_discover", driver=args.driver, count=len(descriptors))
    print(json.dumps(
        [{
            "device_local_id": d.device_local_id,
            "kind": d.kind,
            "name": d.name,
            "driver": d.driver,
            "capabilities": list(d.capabilities),
        } for d in descriptors],
        indent=2,
    ))
    return 0


def _cmd_telemetry(args) -> int:
    adapter = _load_adapter(args.driver)
    try:
        sample = adapter.read_device(args.device_id)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        audit("cli_telemetry_error",
              driver=args.driver, device=args.device_id, error=str(e))
        return 2
    audit("cli_telemetry",
          driver=args.driver, device=args.device_id, kind=sample.kind)
    print(json.dumps({
        "device_local_id": sample.device_local_id,
        "kind": sample.kind,
        "ts": sample.ts_iso,
        "fields": sample.fields,
    }, indent=2, default=str))
    return 0


def _cmd_poll(args) -> int:
    from astroscan_bridge.service.poller import poll_loop
    poll_loop(_load_adapter(args.driver), interval_s=args.interval)
    return 0


def _cmd_cloud_pair(args) -> int:
    from astroscan_bridge.cloud.client import CloudBridgeClient, mask_token

    adapter = _load_adapter(args.driver)
    client = CloudBridgeClient(args.base_url, args.agent_id, timeout_s=args.timeout)
    try:
        descriptors = adapter.discover()
        device_payload = [{
            "device_local_id": d.device_local_id,
            "kind": d.kind,
            "name": d.name,
            "driver": d.driver,
            "capabilities": list(d.capabilities),
        } for d in descriptors]
        audit("cloud_discover",
              driver=args.driver, agent_id=args.agent_id, count=len(device_payload))

        token = client.pair_request(label=args.label)
        audit("cloud_pair_request",
              agent_id=args.agent_id, token=mask_token(token))

        confirm = client.pair_confirm(token, device_payload)
        audit("cloud_pair_confirm",
              agent_id=args.agent_id, status=confirm.get("status"),
              devices=len(device_payload))

        print(json.dumps({
            "agent_id": args.agent_id,
            "devices_count": len(device_payload),
            "pair_request": {"pairing_token": mask_token(token)},
            "pair_confirm": confirm,
        }, indent=2, default=str))
        return 0 if confirm.get("status") == "paired" else 1
    finally:
        client.close()
        adapter.close()


def _cmd_cloud_run(args) -> int:
    from astroscan_bridge.cloud.client import CloudBridgeClient, mask_token

    adapter = _load_adapter(args.driver)
    client = CloudBridgeClient(args.base_url, args.agent_id, timeout_s=args.timeout)

    descriptors = adapter.discover()
    device_payload = [{
        "device_local_id": d.device_local_id,
        "kind": d.kind,
        "name": d.name,
        "driver": d.driver,
        "capabilities": list(d.capabilities),
    } for d in descriptors]
    audit("cloud_run_start",
          driver=args.driver, agent_id=args.agent_id,
          devices=len(device_payload), interval_s=args.interval)

    iteration = 0
    try:
        if client.is_paired():
            print(json.dumps({
                "event": "already_paired",
                "agent_id": args.agent_id,
                "devices_count": len(device_payload),
            }), flush=True)
            audit("cloud_pair_skip", agent_id=args.agent_id, reason="already_paired")
        else:
            token = client.pair_request(label=args.label)
            audit("cloud_pair_request",
                  agent_id=args.agent_id, token=mask_token(token))
            confirm = client.pair_confirm(token, device_payload)
            audit("cloud_pair_confirm",
                  agent_id=args.agent_id, status=confirm.get("status"))
            print(json.dumps({
                "event": "paired",
                "agent_id": args.agent_id,
                "result": confirm,
            }), flush=True)

        while True:
            iteration += 1
            samples: list[dict] = []
            for d in descriptors:
                try:
                    sample = adapter.read_device(d.device_local_id)
                    samples.append({
                        "device_local_id": sample.device_local_id,
                        "kind": sample.kind,
                        "ts": sample.ts_iso,
                        "fields": sample.fields,
                    })
                except Exception as exc:
                    audit("cloud_telemetry_read_error",
                          device=d.device_local_id,
                          error=f"{exc.__class__.__name__}: {exc}")

            push_status: str
            try:
                push = client.telemetry_push({
                    "iteration": iteration,
                    "samples": samples,
                })
                push_status = str(push.get("status") or "unknown")
            except Exception as exc:
                push_status = f"error:{exc.__class__.__name__}"
                audit("cloud_telemetry_push_error",
                      iteration=iteration, error=f"{exc.__class__.__name__}: {exc}")

            audit("cloud_telemetry_push",
                  iteration=iteration, samples=len(samples), status=push_status)
            print(json.dumps({
                "iteration": iteration,
                "samples": len(samples),
                "push": push_status,
            }), flush=True)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(json.dumps({"event": "interrupted"}), flush=True)
        return 0
    finally:
        audit("cloud_run_stop",
              agent_id=args.agent_id, iterations=iteration)
        client.close()
        adapter.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="astroscan-bridge",
        description="AstroScan Telescope Bridge Agent — read-only telemetry (TB-3.1).",
    )
    parser.add_argument(
        "--driver",
        choices=("mock", "alpaca"),
        default="mock",
        help="Adapter to use. TB-3.2 supports 'mock' and 'alpaca'.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover", help="Enumerate devices and exit.")

    p_tel = sub.add_parser("telemetry", help="Read one device and exit.")
    p_tel.add_argument("--device-id", required=True,
                       help="device_local_id from `discover`.")

    p_poll = sub.add_parser("poll", help="Continuously read all devices.")
    p_poll.add_argument("--interval", type=int, default=5,
                        help="Seconds between cycles (default 5).")

    def _add_cloud_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--base-url", required=True,
                       help="AstroScan cloud bridge base URL "
                            "(e.g. http://127.0.0.1:5003/api/telescope-bridge).")
        p.add_argument("--agent-id", required=True,
                       help="Stable identifier for this bridge agent.")
        p.add_argument("--label", default="AstroScan Bridge Agent",
                       help="Human-readable label sent with the pairing request.")
        p.add_argument("--timeout", type=float, default=5.0,
                       help="HTTP timeout in seconds (default 5).")

    p_pair = sub.add_parser("cloud-pair",
                            help="Discover devices then pair with the AstroScan cloud.")
    _add_cloud_common(p_pair)

    p_run = sub.add_parser("cloud-run",
                           help="Ensure paired, then push telemetry on an interval.")
    _add_cloud_common(p_run)
    p_run.add_argument("--interval", type=int, default=10,
                       help="Seconds between telemetry pushes (default 10).")

    args = parser.parse_args(argv)
    handlers = {
        "discover": _cmd_discover,
        "telemetry": _cmd_telemetry,
        "poll": _cmd_poll,
        "cloud-pair": _cmd_cloud_pair,
        "cloud-run": _cmd_cloud_run,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
