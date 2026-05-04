"""Shared HTTP client (connection-pooled) — PASS 29.

A pre-configured `requests.Session` with retry/backoff and connection
pooling, intended for **new code only**. Existing routes that import
`requests` directly, or that use the curl-based helpers in
`app.services.http_client` (PASS 8), are NOT migrated — backward
compatibility is preserved.

The PASS 29 prompt asked for this module to live at
`app/services/http_client.py`, but that path is already occupied by the
curl-based helpers used by 8 modules (feeds, ai, cameras, iss, etc.).
Renaming to `http_pool.py` avoids breaking those consumers.

Why a shared session?
- Connection pooling avoids per-call TLS handshake costs when an
  endpoint hits the same upstream repeatedly (NASA, ip-api, etc.).
- Centralised retry policy: transient 5xx and connection errors are
  retried with exponential backoff, so callers don't reimplement it.
- A consistent User-Agent identifies AstroScan to upstreams.

Usage:
    from app.services.http_pool import http_get, http_post, http_request

    r = http_get("https://api.example.com/data", params={"k": "v"})
    r.raise_for_status()
    data = r.json()

The session is created lazily on first call (`_get_session`) so importing
this module is cheap.
"""
import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

_USER_AGENT = "AstroScan/2.0 (+https://astroscan.space)"
_DEFAULT_TIMEOUT = 10
_session: Optional[requests.Session] = None


def _build_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=retry,
    )
    s = requests.Session()
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({"User-Agent": _USER_AGENT})
    return s


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _build_session()
        log.debug("[http_pool] shared session initialised")
    return _session


def http_request(
    method: str,
    url: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    **kw: Any,
) -> requests.Response:
    """Send an HTTP request through the shared session.

    Equivalent to `requests.request(method, url, ...)` but uses the
    pooled session with retry/backoff and the AstroScan User-Agent.
    """
    return _get_session().request(method, url, timeout=timeout, **kw)


def http_get(url: str, *, timeout: float = _DEFAULT_TIMEOUT, **kw: Any) -> requests.Response:
    """GET via the shared session. Same kwargs as `requests.get`."""
    return _get_session().get(url, timeout=timeout, **kw)


def http_post(url: str, *, timeout: float = _DEFAULT_TIMEOUT, **kw: Any) -> requests.Response:
    """POST via the shared session. Same kwargs as `requests.post`."""
    return _get_session().post(url, timeout=timeout, **kw)
