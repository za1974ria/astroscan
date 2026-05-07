"""Service tle_cache — cache TLE partagé (mutable dict, identity-stable).

Extrait depuis station_web.py L868-L877 lors de PASS 23.5 (après refactor
mutation in-place de fetch_tle_from_celestrak en PHASE α).

Contrat d'identité (CRITIQUE) :
  - `TLE_CACHE` est un dict mutable créé une seule fois au chargement de ce
    module. Tous les consommateurs (8 blueprints + station_web.py) doivent
    accéder via ce module ou via le re-export `from station_web import
    TLE_CACHE` afin de partager la même instance.
  - Toute mise à jour DOIT se faire par mutation in-place :
        TLE_CACHE.clear(); TLE_CACHE.update({...})
        TLE_CACHE[<key>] = <val>
        TLE_CACHE.update(<key>=<val>, ...)
    Une réassignation `TLE_CACHE = {...}` à l'échelle d'un module casserait
    l'invariant et provoquerait une divergence silencieuse entre lecteurs.

station_web.py conserve un alias re-export pour la compat des imports
legacy : `from station_web import TLE_CACHE` et `from station_web import
TLE_CACHE_FILE` continuent de fonctionner.
"""

from app.services.station_state import STATION

# PASS 20.2 (2026-05-08) — Façade unifiée des 5 helpers/globals TLE+Satellites :
# - TLE_CACHE (mutable dict, défini ici, identity-stable)
# - TLE_CACHE_FILE (path JSON cache, défini ici)
# - TLE_MAX_SATELLITES (constante limite, déplacée depuis station_web.py:4248)
# - _parse_tle_file (re-export depuis app.services.tle)
# - TLE_ACTIVE_PATH (re-export depuis app.services.tle)
# - list_satellites (re-export depuis app.services.satellites)
# Le shim station_web ré-exporte ces noms pour la rétro-compat des imports
# legacy `from station_web import TLE_CACHE`, `from station_web import TLE_MAX_SATELLITES`, etc.
from app.services.tle import (  # noqa: F401 — re-exports
    TLE_ACTIVE_PATH,
    _parse_tle_file,
)
from app.services.satellites import list_satellites  # noqa: F401 — re-export

TLE_CACHE_FILE: str = f"{STATION}/data/tle_active_cache.json"

# Limite haute de satellites considérés (taille catalogue active TLE).
# Déplacé depuis station_web.py:4248 lors de PASS 20.2.
TLE_MAX_SATELLITES: int = 200

TLE_CACHE: dict = {
    "status": "cached",
    "source": "CelesTrak GP active",
    "last_refresh_iso": None,
    "count": 0,
    "items": [],
    "error": None,
}

__all__ = [
    "TLE_CACHE",
    "TLE_CACHE_FILE",
    "TLE_MAX_SATELLITES",
    "TLE_ACTIVE_PATH",
    "_parse_tle_file",
    "list_satellites",
]
