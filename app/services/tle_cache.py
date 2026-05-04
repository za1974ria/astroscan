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

TLE_CACHE_FILE: str = f"{STATION}/data/tle_active_cache.json"

TLE_CACHE: dict = {
    "status": "cached",
    "source": "CelesTrak GP active",
    "last_refresh_iso": None,
    "count": 0,
    "items": [],
    "error": None,
}
