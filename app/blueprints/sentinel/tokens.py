"""Role-bound signed tokens (parent / driver).

Two distinct tokens are minted per protected trip. The role is sealed
into the signed payload, max_age == server-side TTL. Defence in depth:
the DB row also independently enforces ``expires_at``.
"""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app

_SALT = "sentinel-v1"


def _serializer() -> URLSafeTimedSerializer:
    """Return signer.

    Effective signing key combines BOTH SENTINEL_SECRET_KEY (env, if set) and
    the per-app Flask SECRET_KEY, so signature validation isolates tokens at
    two levels:

      - SENTINEL_SECRET_KEY isolates Sentinel from Flask SECRET_KEY leaks
        (audit P1-4, 2026-05-15): even if SECRET_KEY surfaces via a debug
        toolbar / unhandled traceback / Sentry payload, the attacker cannot
        forge Sentinel tokens without the env-only sentinel secret.
      - The Flask SECRET_KEY component prevents tokens from crossing Flask
        application instances that share SENTINEL_SECRET_KEY but have
        distinct SECRET_KEYs (different deployments, multi-tenant, test
        isolation). Without this component, two Flask apps with different
        SECRET_KEYs would accept each other's tokens when SENTINEL_SECRET_KEY
        is set — a real bypass of per-app signature isolation.

    When SENTINEL_SECRET_KEY is unset, the signer reduces to Flask SECRET_KEY
    alone (legacy / dev behaviour, zero migration cost).
    """
    import os
    sentinel_key = os.environ.get("SENTINEL_SECRET_KEY", "").strip()
    flask_key = str(current_app.config["SECRET_KEY"])
    effective = (sentinel_key + "::" + flask_key) if sentinel_key else flask_key
    return URLSafeTimedSerializer(effective, salt=_SALT)


def make_tokens(session_id: str) -> tuple[str, str]:
    s = _serializer()
    return (
        s.dumps({"sid": session_id, "role": "parent"}),
        s.dumps({"sid": session_id, "role": "driver"}),
    )


class TokenError(Exception):
    pass


def load_token(
    token: str, max_age_seconds: int, expected_role: str | None = None
) -> dict:
    try:
        payload = _serializer().loads(token, max_age=max_age_seconds)
    except SignatureExpired:
        raise TokenError("expired")
    except BadSignature:
        raise TokenError("invalid")
    except Exception:
        raise TokenError("invalid")
    if not isinstance(payload, dict) or "sid" not in payload or "role" not in payload:
        raise TokenError("malformed")
    if expected_role is not None and payload["role"] != expected_role:
        raise TokenError("wrong_role")
    return payload
