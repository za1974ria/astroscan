"""PASS 21.3 (2026-05-08) — Skyview sync thread.

Extrait depuis station_web.py:3974-3982 lors de PASS 21.3.

Démarre un thread daemon qui appelle ``_sync_skyview_to_lab()`` toutes
les 60 secondes pour copier les images du dossier SkyView vers le
répertoire RAW_IMAGES du laboratoire et générer les métadonnées
associées.

Consommateur : ``app/bootstrap.py:52`` qui importe
``from station_web import _start_skyview_sync`` et appelle la fonction
au démarrage du process.

Réutilisation : ``_sync_skyview_to_lab()`` est défini dans
``app/services/lab_helpers.py`` (PASS 20.3) — le worker ne fait
qu'orchestrer la boucle d'appel périodique.

Lazy import inside la boucle pour ``_sync_skyview_to_lab`` afin de
préserver la même résolution que dans station_web (importé depuis
``app.services.lab_helpers``, mais via le shim station_web la fonction
y est aussi accessible — on choisit l'import canonique direct depuis
le service).
"""
from __future__ import annotations

import threading
import time


def _start_skyview_sync():
    """Boucle de sync SkyView → Lab toutes les 60 secondes."""
    def loop():
        # Lazy import : évite le cycle station_web ↔ skyview_sync au load.
        # Au moment du premier tour, station_web est entièrement chargé
        # et lab_helpers.py est résolu (le service est sans dépendance
        # inverse vers station_web au load).
        from app.services.lab_helpers import _sync_skyview_to_lab

        while True:
            _sync_skyview_to_lab()
            time.sleep(60)

    t = threading.Thread(target=loop, daemon=True)
    t.start()


__all__ = ["_start_skyview_sync"]
