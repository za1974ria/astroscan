"""
Source unique de vérité pour les coordonnées de l'observatoire ASTRO-SCAN.

ATTENTION CRITIQUE :
- Tlemcen est à l'OUEST du méridien de Greenwich.
- Longitude = -1.3167 (NÉGATIVE).
- Ne JAMAIS écrire +1.3167 ou +1.32 (placerait la station à Tiaret, ~300 km est).

Référence officielle : Google Maps coordinates for Tlemcen, Algeria
https://www.google.com/maps/place/Tlemcen

Toute modification de ce fichier doit être justifiée et auditée.
"""

OBSERVER_CITY = "Tlemcen, Algérie"
OBSERVER_COUNTRY = "DZ"
OBSERVER_LAT = 34.8753       # °N
OBSERVER_LON = -1.3167       # °W (NÉGATIF — OUEST de Greenwich)
OBSERVER_ALT_M = 816         # mètres
OBSERVER_TIMEZONE = "Africa/Algiers"  # UTC+1, pas de DST en Algérie

# Alias historiques pour compatibilité
TLEMCEN_LAT = OBSERVER_LAT
TLEMCEN_LON = OBSERVER_LON
TLEMCEN_ALT = OBSERVER_ALT_M

# Forme dict pour APIs JSON
OBSERVER_DICT = {
    "city": OBSERVER_CITY,
    "country": OBSERVER_COUNTRY,
    "lat": OBSERVER_LAT,
    "lon": OBSERVER_LON,
    "alt_m": OBSERVER_ALT_M,
    "timezone": OBSERVER_TIMEZONE,
}

# Forme tuple (Skyfield, astropy)
OBSERVER_TUPLE = (OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M)
