"""Service status_engine — wrapper d'import sécurisé vers core.status_engine.

Extrait depuis station_web.py L613-L616 lors de PASS 23.

Pattern : on tente l'import du module `core.status_engine` (helpers santé
opérationnelle / crédibilité données). En cas d'échec d'import, la variable
`_core_status_engine` vaut `None` — les blueprints consommateurs (health_bp)
testent `is not None` avant tout appel.

station_web.py conserve un alias re-export pour la compat des imports legacy
(`from station_web import _core_status_engine` ou `_sw._core_status_engine`).
"""

try:
    from core import status_engine as _core_status_engine
except Exception:
    _core_status_engine = None
