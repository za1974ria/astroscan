"""HTTP client helpers — curl wrappers + safe JSON parsing.

Extrait de station_web.py (PASS 8) pour permettre l'utilisation
par feeds_bp et autres BPs sans dépendance circulaire.

Pourquoi curl plutôt que urllib/requests ?
  Le serveur de production à Tlemcen a des restrictions réseau qui
  empêchent urllib de fonctionner correctement avec certaines API
  (notamment NASA/JPL Horizons). curl contourne ces limitations.

Note : station_web.py garde sa propre copie identique pour ne pas
casser les routes monolithe restantes (single source of truth viendra
en PASS final).
"""
from __future__ import annotations

import json
import logging
import subprocess
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def _curl_get(url: str, timeout: int = 15) -> str:
    """GET via curl — contourne restrictions réseau urllib."""
    try:
        r = subprocess.run(
            [
                "curl", "-s", "-L", "--max-time", str(timeout),
                "-H", "User-Agent: ORBITAL-CHOHRA/1.0",
                url,
            ],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        return (r.stdout or "").strip()
    except Exception as e:
        log.warning("curl_get %s: %s", url[:60], e)
        return ""


def _curl_post(
    url: str,
    post_data: str,
    timeout: int = 15,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """POST via curl (JSON body). headers optionnel (ex. x-api-key)."""
    try:
        cmd = [
            "curl", "-s", "-L", "--max-time", str(timeout),
            "-H", "User-Agent: ORBITAL-CHOHRA/1.0",
            "-H", "Content-Type: application/json", "-X", "POST", "-d", post_data,
        ]
        if headers:
            for k, v in headers.items():
                if v is not None and str(v).strip() != "":
                    cmd.extend(["-H", f"{k}: {v}"])
        cmd.append(url)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        return (r.stdout or "").strip()
    except Exception as e:
        log.warning("curl_post %s: %s", url[:60], e)
        return None


def _curl_post_json(
    url: str,
    payload_dict: Any,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
) -> Optional[str]:
    """POST JSON body (dict) avec headers optionnels."""
    body = json.dumps(payload_dict) if isinstance(payload_dict, dict) else payload_dict
    return _curl_post(url, body, timeout=timeout, headers=extra_headers)


def _safe_json_loads(raw: str, label: str = "json") -> Any:
    """json.loads avec log warning si échec (ne lève pas)."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        log.warning("safe_json_loads[%s]: %s (raw[:80]=%r)", label, e, raw[:80])
        return None
