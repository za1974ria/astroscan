"""Read-only HTTP session — runtime defense against any write verb.

`ReadOnlyHttpSession` extends `requests.Session` and overrides the
single chokepoint method `request()` so that ANY HTTP verb other than
GET or HEAD raises `WriteAttemptError` BEFORE the network call is made.

Why subclass `Session` rather than expose only a `get(url)` helper:
Convenience methods on `requests.Session` (`session.put`, `session.post`,
`session.delete`, `session.patch`) all funnel through `Session.request`.
Overriding `request` gives us a single guarded entry point that no
caller can bypass — even monkey-patched or maintenance-mutated code
paths fall through this guard.

Why HEAD is allowed alongside GET: it is the canonical read-only probe
for resource existence and ETag inspection. It performs no mutation.

This module imports ONLY `requests` from the runtime ecosystem and the
local `WriteAttemptError` exception type.
"""
from __future__ import annotations

import requests

from astroscan_bridge.safety.readonly_filter import WriteAttemptError


# Set of HTTP verbs the agent is allowed to send. Frozen by construction;
# any future change requires a security review.
_ALLOWED_HTTP_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})


class ReadOnlyHttpSession(requests.Session):
    """A `requests.Session` that refuses every non-read HTTP method.

    Verbs blocked at the session layer (raise `WriteAttemptError`):
        PUT, POST, DELETE, PATCH, OPTIONS, TRACE, CONNECT, and any
        custom/lowercase variant.

    Verbs allowed:
        GET, HEAD — both are read-only by the HTTP specification.
    """

    def request(self, method, url, *args, **kwargs):  # type: ignore[override]
        if str(method).upper() not in _ALLOWED_HTTP_METHODS:
            raise WriteAttemptError(
                f"AstroScan Bridge is read-only; HTTP {method!r} is blocked "
                f"(target URL was: {url})"
            )
        return super().request(method, url, *args, **kwargs)
