"""PASS 23.3 (2026-05-08) — HTTP helpers façade.

Façade unifiée pour les 4 helpers HTTP utilisés par station_web et les
blueprints :

- ``_emit_diag_json(payload)`` : extrait depuis station_web.py:120-133,
  émetteur de logs JSON diagnostiques (stdout + logger).
- ``_curl_get`` / ``_curl_post`` / ``_curl_post_json`` : re-exports depuis
  ``app.services.http_client`` (qui était le module canonique pré-existant
  pour les wrappers curl, créé en PASS 8).

Pourquoi cette façade ?
station_web.py contenait jusqu'à PASS 23.2 une **duplication** des 3 helpers
``_curl_*`` (versions identiques fonctionnellement à celles de
``http_client.py``). PASS 23.3 résout cette duplication :
- ``http_helpers.py`` ré-exporte les 3 noms depuis ``http_client.py``
  (single source of truth)
- ``_emit_diag_json`` est unifié ici (n'existait que dans station_web)
- Le shim ``station_web`` ré-exporte les 4 noms depuis cette façade

PRESERVED in station_web (cf. PASS 23.3 prompt) :
- ``_requests_instrumented_request`` : monkey-patch appliqué à
  ``requests.sessions.Session.request`` au load — DOIT rester dans
  station_web pour que l'instrumentation reste globale.
- ``_REQ_ORIGINAL_REQUEST`` : référence backup utilisée par le monkey-patch.

``_emit_diag_json`` utilise ``log`` (logger station_web) — lazy import
inside pour éviter le cycle au load.
"""
from __future__ import annotations

import json

# Re-exports depuis le module canonique http_client (PASS 8)
from app.services.http_client import (  # noqa: F401 — re-exports
    _curl_get,
    _curl_post,
    _curl_post_json,
)


def _emit_diag_json(payload) -> None:
    """Émet un JSON diagnostique en stdout + logger."""
    try:
        msg = json.dumps(payload, ensure_ascii=False)
    except Exception:
        msg = json.dumps({"event": "diag_encode_failed"}, ensure_ascii=False)
    try:
        print(msg, flush=True)
    except Exception:
        pass
    try:
        # Lazy import : log est défini dans station_web (logger.getLogger(__name__)),
        # cycle-safe car _emit_diag_json est appelé post-init.
        from station_web import log
        log.info(msg)
    except Exception:
        pass


__all__ = [
    "_emit_diag_json",
    "_curl_get",
    "_curl_post",
    "_curl_post_json",
]
