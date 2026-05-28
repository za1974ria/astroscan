"""TB-35 — AstroScan cloud bridge HTTP client.

Talks to the cloud bridge blueprint mounted at <base_url> (typically
http://127.0.0.1:5003/api/telescope-bridge). The telescope hardware is
NEVER touched from this module: every URL is checked against the
operator-supplied base URL before any non-GET method is allowed.

Design rules (TB-35 safety posture):
  - GET/HEAD allowed anywhere (read-only by definition).
  - POST allowed ONLY to the cloud base URL, ONLY on a fixed
    allowlist of paths (pair_request / pair_confirm / telemetry_push).
  - Every other HTTP method raises WriteAttemptError.
  - No subprocess, no os.system, no shell, no filesystem writes.
  - Payloads are forced through json.loads(json.dumps(..., default=str))
    so a bad adapter return cannot leak non-serializable objects to
    the wire.
  - All HTTP calls carry a finite timeout.
  - Retries are intentionally minimal (1 retry for telemetry push only).
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

from astroscan_bridge.safety.readonly_filter import WriteAttemptError


# Paths (relative to base_url) that the cloud client is allowed to POST to.
# Anything else MUST raise WriteAttemptError. Keep this list short and
# explicit — extending it requires a security review.
_ALLOWED_POST_PATHS: tuple[str, ...] = (
    "/pair/request",
    "/pair/confirm",
    "/telemetry/push",
)


class CloudHttpSession(requests.Session):
    """A `requests.Session` constrained to the AstroScan cloud bridge.

    Sibling of `astroscan_bridge.safety.http_guard.ReadOnlyHttpSession`,
    which remains the ONLY session used by the telescope-hardware
    adapters. This session permits POST exclusively to the configured
    cloud base URL on a small allowlist of paths.
    """

    def __init__(self, allowed_base: str):
        super().__init__()
        parsed = urlparse(allowed_base)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"unsupported cloud base url: {allowed_base!r}")
        self._allowed_scheme = parsed.scheme
        self._allowed_netloc = parsed.netloc
        self._allowed_path_prefix = parsed.path.rstrip("/")

    def request(self, method, url, *args, **kwargs):
        m = str(method).upper()
        if m in ("GET", "HEAD"):
            return super().request(method, url, *args, **kwargs)
        if m != "POST":
            raise WriteAttemptError(f"HTTP method blocked: {method}")

        parsed = urlparse(str(url))
        if (
            parsed.scheme != self._allowed_scheme
            or parsed.netloc != self._allowed_netloc
            or not parsed.path.startswith(self._allowed_path_prefix)
        ):
            raise WriteAttemptError(f"POST denied (off-base url): {url}")

        tail = parsed.path[len(self._allowed_path_prefix):] or "/"
        if tail not in _ALLOWED_POST_PATHS:
            raise WriteAttemptError(f"POST denied (path not allowlisted): {tail}")

        return super().request(method, url, *args, **kwargs)


def _json_safe(value: Any) -> Any:
    """Force `value` through a JSON round-trip to guarantee the payload
    is a JSON-serializable primitive tree before it hits the wire."""
    return json.loads(json.dumps(value, default=str))


def mask_token(token: str | None) -> str:
    if not token or len(token) < 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


class CloudBridgeClient:
    """High-level client for the AstroScan cloud bridge.

    Stateless across CLI invocations: pairing is re-checked from
    `GET /devices` on every cloud-run start.
    """

    def __init__(self, base_url: str, agent_id: str, timeout_s: float = 5.0):
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id.strip()
        self.timeout_s = float(timeout_s)
        self.session = CloudHttpSession(self.base_url)

    # -- low-level transport --------------------------------------------------

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        body = _json_safe(payload)
        res = self.session.post(url, json=body, timeout=self.timeout_s)
        res.raise_for_status()
        return res.json()

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        res = self.session.get(url, timeout=self.timeout_s)
        res.raise_for_status()
        return res.json()

    # -- pairing --------------------------------------------------------------

    def pair_request(self, label: str = "AstroScan Bridge Agent") -> str:
        data = self._post("/pair/request", {"label": label})
        token = data.get("pairing_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError(f"pair_request returned no pairing_token: {data}")
        return token

    def pair_confirm(self, token: str, devices: Iterable[Any]) -> dict:
        device_list = [_json_safe(d) for d in devices]
        return self._post("/pair/confirm", {
            "pairing_token": token,
            "agent_id": self.agent_id,
            "devices": device_list,
        })

    # -- telemetry ------------------------------------------------------------

    def telemetry_push(self, telemetry: Any, retries: int = 1) -> dict:
        payload = {
            "agent_id": self.agent_id,
            "telemetry": _json_safe(telemetry),
        }
        last_exc: Exception | None = None
        attempts = max(1, int(retries) + 1)
        for i in range(attempts):
            try:
                return self._post("/telemetry/push", payload)
            except Exception as exc:
                last_exc = exc
                if i + 1 < attempts:
                    time.sleep(0.5)
        assert last_exc is not None
        raise last_exc

    # -- discovery ------------------------------------------------------------

    def list_devices(self) -> dict:
        return self._get("/devices")

    def is_paired(self) -> bool:
        try:
            data = self.list_devices()
        except Exception:
            return False
        devices = data.get("devices") or []
        if isinstance(devices, dict):
            return self.agent_id in devices
        for entry in devices:
            if isinstance(entry, dict) and entry.get("agent_id") == self.agent_id:
                return True
        return False

    def close(self) -> None:
        self.session.close()
