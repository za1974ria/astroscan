"""PASS 23.2 (2026-05-08) — Metrics service (in-memory).

Extrait depuis station_web.py:455-505 lors de PASS 23.2.

Métriques in-memory pour /status (léger, pas de DB) :
- ``_metrics_trim_list(ts_list, horizon_sec)`` : utilitaire de rognage
- ``metrics_record_request()`` : enregistre une requête HTTP
- ``metrics_record_struct_error()`` : compte les events ERROR
- ``metrics_status_fields()`` : payload pour /status (errors_last_5min,
  requests_per_min)

Architecture :
- Fenêtres glissantes : timestamps en ``time.time()``.
- Lock courte ``_METRICS_LOCK`` pour limiter la contention.
- Rognage périodique + plafond de taille → O(window) borné, pas de fuite mémoire.

Mutables globals :
- ``_METRICS_REQUEST_TIMES``, ``_METRICS_ERROR_TIMES`` sont des listes
  mutées **in-place** (``.append()``, ``del list[:N]``, ``list[:] = …``).
  L'identité est préservée — même comportement que ``TLE_CACHE`` du
  PASS 20.2.
- ``_METRICS_LOCK`` est un Lock object (non réassigné).
- ``_METRICS_MAX_REQ_BUFFER`` est un int constant.

Aucun consommateur externe n'importe ces globals → restent privés au module.
Seules les 4 fonctions sont ré-exportées via le shim station_web.

Module standalone : aucun import depuis station_web ou autres services au load.
"""
from __future__ import annotations

import threading
import time

# ── Métriques in-memory pour /status (léger, pas de DB) ─────────────
# Fenêtres glissantes : timestamps en time.time(). Lock courte pour limiter
# la contention ; rognage périodique + plafond de taille → O(window) borné.
_METRICS_LOCK = threading.Lock()
_METRICS_REQUEST_TIMES: list[float] = []
_METRICS_ERROR_TIMES: list[float] = []
_METRICS_MAX_REQ_BUFFER: int = 12000


def _metrics_trim_list(ts_list: list[float], horizon_sec: float) -> None:
    cutoff = time.time() - horizon_sec
    ts_list[:] = [t for t in ts_list if t >= cutoff]


def metrics_record_request() -> None:
    """Enregistre une requête HTTP (appelé depuis after_request, hors /static)."""
    try:
        t = time.time()
        with _METRICS_LOCK:
            _METRICS_REQUEST_TIMES.append(t)
            _metrics_trim_list(_METRICS_REQUEST_TIMES, 360)
            if len(_METRICS_REQUEST_TIMES) > _METRICS_MAX_REQ_BUFFER:
                del _METRICS_REQUEST_TIMES[: len(_METRICS_REQUEST_TIMES) - _METRICS_MAX_REQ_BUFFER + 2000]
    except Exception:
        pass


def metrics_record_struct_error() -> None:
    """Compte les événements struct_log au niveau ERROR (observabilité /status)."""
    try:
        t = time.time()
        with _METRICS_LOCK:
            _METRICS_ERROR_TIMES.append(t)
            _metrics_trim_list(_METRICS_ERROR_TIMES, 360)
            if len(_METRICS_ERROR_TIMES) > 4000:
                del _METRICS_ERROR_TIMES[: len(_METRICS_ERROR_TIMES) - 3000]
    except Exception:
        pass


def metrics_status_fields() -> dict:
    """
    Champs additionnels pour /status : erreurs struct_log (niveau ERROR) sur 5 min,
    requêtes non-static sur la dernière minute glissante (débit observé).
    Deux passes sur des listes déjà rognées → coût prévisible même sous charge.
    """
    now = time.time()
    with _METRICS_LOCK:
        e5 = sum(1 for x in _METRICS_ERROR_TIMES if x >= now - 300)
        r60 = sum(1 for x in _METRICS_REQUEST_TIMES if x >= now - 60)
    return {"errors_last_5min": int(e5), "requests_per_min": int(r60)}


__all__ = [
    "_metrics_trim_list",
    "metrics_record_request",
    "metrics_record_struct_error",
    "metrics_status_fields",
]
