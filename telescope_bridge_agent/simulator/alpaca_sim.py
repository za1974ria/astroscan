"""Alpaca local simulator - read-only fake telescope endpoint.

Binds HTTP on 127.0.0.1:11111 and UDP discovery on 0.0.0.0:32227.
Stdlib only. Intended for TB-3.2.1 local validation. NOT for production.
"""
from __future__ import annotations

import json
import logging
import math
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HTTP_HOST = "127.0.0.1"
HTTP_PORT = 11111
UDP_HOST = "0.0.0.0"
UDP_PORT = 32227
DISCOVERY_MAGIC = b"alpacadiscovery1"

LOG = logging.getLogger("alpaca_sim")

CONFIGURED_DEVICES = [
    {"DeviceName": "Sim EQ6-R Pro",  "DeviceType": "Telescope", "DeviceNumber": 0, "UniqueID": "sim-mount-0"},
    {"DeviceName": "Sim ASI2600MM",  "DeviceType": "Camera",    "DeviceNumber": 0, "UniqueID": "sim-cam-0"},
    {"DeviceName": "Sim ZWO EAF",    "DeviceType": "Focuser",   "DeviceNumber": 0, "UniqueID": "sim-focuser-0"},
]


def _telescope_property(prop: str):
    t = time.time()
    table = {
        "connected":      True,
        "rightascension": round((t / 3600.0) % 24.0, 5),
        "declination":    round(20.0 * math.sin(t / 600.0), 3),
        "tracking":       True,
    }
    return table.get(prop)


def _camera_property(prop: str):
    t = time.time()
    table = {
        "connected":      True,
        "ccdtemperature": round(-10.0 + math.sin(t / 100.0), 2),
        "cooleron":       True,
    }
    return table.get(prop)


def _focuser_property(prop: str):
    t = time.time()
    table = {
        "connected":   True,
        "position":    15000 + int(50 * math.sin(t / 30.0)),
        "temperature": 18.5,
    }
    return table.get(prop)


DEVICE_DISPATCH = {
    "telescope": _telescope_property,
    "camera":    _camera_property,
    "focuser":   _focuser_property,
}


class _ServerTxn:
    _lock = threading.Lock()
    _counter = 0

    @classmethod
    def next_id(cls) -> int:
        with cls._lock:
            cls._counter += 1
            return cls._counter


def _alpaca_response(value, error_number: int = 0, error_message: str = "") -> bytes:
    payload = {
        "Value": value,
        "ClientTransactionID": 0,
        "ServerTransactionID": _ServerTxn.next_id(),
        "ErrorNumber": error_number,
        "ErrorMessage": error_message,
    }
    return json.dumps(payload).encode("utf-8")


class AlpacaHandler(BaseHTTPRequestHandler):
    server_version = "AstroScanAlpacaSim/1.0"

    def log_message(self, fmt, *args):
        LOG.info("HTTP %s - %s", self.address_string(), fmt % args)

    def do_HEAD(self):  # noqa: N802
        self._dispatch(write_body=False)

    def do_GET(self):  # noqa: N802
        self._dispatch(write_body=True)

    def _send(self, status: int, body: bytes, content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _dispatch(self, write_body: bool):
        path = urlparse(self.path).path.rstrip("/")

        if path == "/management/apiversions":
            return self._send(200, _alpaca_response([1]) if write_body else b"")

        if path == "/management/v1/description":
            desc = {
                "ServerName": "AstroScanAlpacaSim",
                "Manufacturer": "AstroScan",
                "ManufacturerVersion": "1.0",
                "Location": "loopback",
            }
            return self._send(200, _alpaca_response(desc) if write_body else b"")

        if path == "/management/v1/configureddevices":
            return self._send(200, _alpaca_response(CONFIGURED_DEVICES) if write_body else b"")

        parts = path.strip("/").split("/")
        # api/v1/{device_type}/{number}/{property}
        if len(parts) == 5 and parts[0] == "api" and parts[1] == "v1":
            device_type, number_s, prop = parts[2].lower(), parts[3], parts[4].lower()
            handler = DEVICE_DISPATCH.get(device_type)
            if handler is None:
                return self._send(200, _alpaca_response(None, 1025, f"unknown device type {device_type}"))
            try:
                int(number_s)
            except ValueError:
                return self._send(400, _alpaca_response(None, 1025, "bad device number"))
            value = handler(prop)
            if value is None:
                return self._send(200, _alpaca_response(None, 1024, f"property not implemented: {prop}"))
            return self._send(200, _alpaca_response(value) if write_body else b"")

        return self._send(404, _alpaca_response(None, 1026, "not found"))


def _start_http() -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), AlpacaHandler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="alpaca-http", daemon=True).start()
    LOG.info("HTTP listening on http://%s:%d", HTTP_HOST, HTTP_PORT)
    return srv


def _start_udp() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((UDP_HOST, UDP_PORT))

    def _serve():
        LOG.info("UDP discovery listening on %s:%d", UDP_HOST, UDP_PORT)
        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except OSError:
                return
            if DISCOVERY_MAGIC in data.lower():
                reply = json.dumps({"AlpacaPort": HTTP_PORT}).encode("utf-8")
                try:
                    sock.sendto(reply, addr)
                    LOG.info("UDP discovery reply to %s", addr)
                except OSError as exc:
                    LOG.warning("UDP reply failed: %s", exc)

    threading.Thread(target=_serve, name="alpaca-udp", daemon=True).start()
    return sock


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    http_srv = _start_http()
    udp_sock = _start_udp()
    stop = threading.Event()

    def _handle(_sig, _frm):
        LOG.info("shutdown signal received")
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    try:
        stop.wait()
    finally:
        try:
            http_srv.shutdown()
        except Exception:
            pass
        try:
            udp_sock.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
