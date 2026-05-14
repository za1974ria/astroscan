"""Firebase Cloud Messaging (HTTP v1) — minimal, fail-soft.

Provisioning (server-side, one-time):
  1. Create a Firebase project, enable Cloud Messaging.
  2. Generate a service account key (Project Settings → Service accounts).
  3. Save the JSON to ``/root/.config/sentinel/firebase-sa.json``
     with mode 0600, owner root.
  4. Set env vars (in .env, picked up by station_web/wsgi):
       FCM_PROJECT_ID=your-project-id
       FCM_SERVICE_ACCOUNT_PATH=/root/.config/sentinel/firebase-sa.json

If unprovisioned, ``is_configured()`` returns False and all calls
become no-ops. The Sentinel session lifecycle is unaffected — push
is a notification *layer*, never a hard dependency.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

log = logging.getLogger("astroscan.sentinel.push")

_FCM_BASE = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

_token_cache: dict = {"value": None, "expires_at": 0.0}
_token_lock = threading.Lock()


# ── Configuration helpers ────────────────────────────────────────────

def _service_account_path() -> str:
    return os.environ.get(
        "FCM_SERVICE_ACCOUNT_PATH",
        "/root/.config/sentinel/firebase-sa.json",
    )


def _project_id() -> str:
    return os.environ.get("FCM_PROJECT_ID", "").strip()


def is_configured() -> bool:
    if not _project_id():
        return False
    path = _service_account_path()
    if not os.path.isfile(path):
        return False
    try:
        import jwt  # noqa: F401
        return True
    except ImportError:
        return False


# ── OAuth token (cached 50 min) ──────────────────────────────────────

def _mint_access_token() -> str | None:
    try:
        import jwt
        import requests
    except ImportError:
        return None
    try:
        with open(_service_account_path(), "r") as f:
            sa = json.load(f)
        now = int(time.time())
        claims = {
            "iss": sa["client_email"],
            "scope": _SCOPE,
            "aud": _TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        }
        assertion = jwt.encode(claims, sa["private_key"], algorithm="RS256")
        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            log.warning("[FCM] oauth refused: %s %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        with _token_lock:
            _token_cache["value"] = data["access_token"]
            _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
        return _token_cache["value"]
    except Exception as e:
        log.warning("[FCM] oauth error: %s", e)
        return None


def _access_token() -> str | None:
    with _token_lock:
        if _token_cache["value"] and time.time() < _token_cache["expires_at"] - 60:
            return _token_cache["value"]
    return _mint_access_token()


# ── Outbound send ────────────────────────────────────────────────────

def _send_fcm(fcm_token: str, title: str, body: str, data: dict) -> bool:
    if not is_configured():
        return False
    try:
        import requests
    except ImportError:
        return False
    access = _access_token()
    if not access:
        return False
    url = _FCM_BASE.format(project=_project_id())
    # Data payloads are received in background; notification triggers system UI.
    # Strings only in `data` per FCM spec.
    payload = {
        "message": {
            "token": fcm_token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
            "android": {
                "priority": "HIGH",
                "notification": {"sound": "default", "channel_id": "sentinel_alerts"},
            },
        }
    }
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {access}",
                "Content-Type": "application/json; charset=utf-8",
            },
            data=json.dumps(payload),
            timeout=8,
        )
        if resp.status_code in (200, 204):
            return True
        # 404 = stale token: caller may want to clear it from the row.
        log.info("[FCM] send rc=%s body=%s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        log.info("[FCM] send error: %s", e)
        return False


# ── High-level: notify by session + role ────────────────────────────

def _render(event: str, payload: dict, row: dict) -> tuple[str, str]:
    label = row.get("driver_label") or "le conducteur"
    speed_limit = row.get("speed_limit_kmh")
    if event == "sos_triggered":
        return ("🚨 SOS — " + label, "Touchez pour ouvrir le trajet et coordonner")
    if event == "sos_acknowledged":
        return ("Proche prévenu", "Ton SOS a bien été reçu. Restez en contact.")
    if event == "over_speed":
        speed = (payload or {}).get("speed_kmh")
        return ("Vitesse élevée prolongée",
                f"{label} dépasse {speed_limit} km/h depuis 15 s")
    if event == "safe_zone_exit":
        return ("Hors zone rassurante", f"{label} s'est éloigné de la zone définie")
    if event == "signal_lost":
        return ("Signal GPS perdu", f"{label} n'envoie plus de position")
    if event == "low_battery":
        return ("Batterie faible", f"Le téléphone de {label} est en batterie faible")
    if event == "stop_requested":
        by = (payload or {}).get("by", "")
        who = "Votre proche" if by == "parent" else f"{label}"
        return ("Fin de trajet demandée",
                f"{who} demande la fin du trajet protégé. Approuver dans l'app.")
    if event == "stop_approved":
        return ("Fin de trajet approuvée", "Le trajet protégé est terminé.")
    if event == "session_expired":
        return ("Trajet expiré", "La durée du trajet protégé est écoulée.")
    return ("Sentinel", event.replace("_", " "))


def notify(session_id: str, target_role: str, event: str, payload: dict | None = None) -> bool:
    """Send a push to the target_role of ``session_id``.

    ``target_role`` ∈ {"parent","driver","both"}. Fail-soft: returns
    False if anything's missing — never raises into the calling code.
    """
    if not is_configured():
        return False
    try:
        from app.blueprints.sentinel import store
    except Exception:
        return False
    row = store.get_session(session_id)
    if not row:
        return False

    if target_role == "both":
        a = notify(session_id, "parent", event, payload)
        b = notify(session_id, "driver", event, payload)
        return a or b

    if target_role == "parent":
        fcm = row.get("parent_fcm_token")
    elif target_role == "driver":
        fcm = row.get("driver_fcm_token")
    else:
        return False
    if not fcm:
        return False

    title, body = _render(event, payload or {}, row)
    data = {"event": event, "session_id": session_id}
    if payload:
        for k, v in payload.items():
            if k in ("lat", "lon", "latitude", "longitude"):
                continue
            data[k] = v
    ok = _send_fcm(fcm, title, body, data)
    log.info("[FCM] notify session=%s role=%s event=%s ok=%s",
             session_id, target_role, event, ok)
    return ok
