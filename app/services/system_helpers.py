"""PASS 20.4 (2026-05-08) — System status / accuracy helpers.

Façade unifiée pour les helpers de statut système consommés par
api_bp et health_bp via lazy imports ``from station_web import …`` :

- ``STATION``           : path racine déploiement (re-export depuis
                          app.services.station_state)
- ``START_TIME``        : timestamp Unix de démarrage du module
                          (déplacé depuis station_web.py:178)
- ``get_accuracy_history``, ``get_accuracy_stats`` : re-exports depuis
                          app.services.accuracy_history (déjà extraits
                          lors d'un PASS antérieur)

Note : ``server_ready`` (bool mutable top-level dans station_web qui
passe de False à True à la fin du boot) est volontairement NON migré.
La sémantique de réassignation top-level d'un bool ne se transmet pas
proprement à un module externe sans wrapper, et changer l'API
(getter/setter) violerait la contrainte ``DO NOT touch any blueprint
file``. Le bool reste donc dans station_web.py.
"""
from __future__ import annotations

import time

from app.services.station_state import STATION
from app.services.accuracy_history import (  # noqa: F401 — re-exports
    get_accuracy_history,
    get_accuracy_stats,
)

# START_TIME : capturé au premier import de ce module.
# Pour le boot monolith, ce module est importé tôt via le shim de
# station_web → la valeur est très proche du démarrage du process.
START_TIME: float = time.time()

__all__ = [
    "STATION",
    "START_TIME",
    "get_accuracy_history",
    "get_accuracy_stats",
]
