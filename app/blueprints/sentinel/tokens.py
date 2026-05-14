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
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


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
