import math
from datetime import datetime, timezone

from astropy.coordinates import (
    EarthLocation, AltAz, get_body, SkyCoord, GeocentricMeanEcliptic,
)
from astropy.time import Time
import astropy.units as u

# Coordonnées Tlemcen (Algérie)
LAT = 34.88
LON = 1.32
ALT_M = 800
LOCATION = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ALT_M * u.m)

# Catalogue DSO — coordonnées J2000 (degrés)
DSO_CATALOG = [
    {'nom': "Nébuleuse d'Orion (M42)",          'ra': 83.82,  'dec': -5.39,  'type': 'nébuleuse'},
    {'nom': 'Pléiades (M45)',                    'ra': 56.75,  'dec': 24.12,  'type': 'amas ouvert'},
    {'nom': 'Nébuleuse du Crabe (M1)',           'ra': 83.63,  'dec': 22.01,  'type': 'nébuleuse'},
    {'nom': "Galaxie d'Andromède (M31)",         'ra': 10.68,  'dec': 41.27,  'type': 'galaxie'},
    {'nom': 'Galaxie Sombrero (M104)',           'ra': 189.99, 'dec': -11.62, 'type': 'galaxie'},
    {'nom': 'Galaxie du Tourbillon (M51)',       'ra': 202.47, 'dec': 47.20,  'type': 'galaxie'},
    {'nom': 'Galaxie de Bode (M81)',             'ra': 148.89, 'dec': 69.07,  'type': 'galaxie'},
    {'nom': 'Nébuleuse du Lagon (M8)',           'ra': 270.93, 'dec': -24.38, 'type': 'nébuleuse'},
    {"Amas d'Hercule (M13)":                     None,
     'nom': "Amas d'Hercule (M13)",              'ra': 250.42, 'dec': 36.46,  'type': 'amas globulaire'},
    {'nom': 'Nébuleuse Amérique du Nord (NGC 7000)', 'ra': 314.75, 'dec': 44.20, 'type': 'nébuleuse'},
    {'nom': 'Double Amas de Persée',             'ra': 34.68,  'dec': 57.04,  'type': 'amas ouvert'},
    {'nom': 'Nuage Étoilé du Sagittaire (M24)',  'ra': 274.32, 'dec': -18.55, 'type': 'amas'},
    {'nom': 'Galaxie du Triangle (M33)',         'ra': 23.46,  'dec': 30.66,  'type': 'galaxie'},
    {'nom': 'Nébuleuse Annulaire (M57)',         'ra': 283.40, 'dec': 33.03,  'type': 'nébuleuse plan.'},
    {'nom': 'Amas du Bouclier (M11)',            'ra': 282.76, 'dec': -6.27,  'type': 'amas ouvert'},
    {'nom': 'Hyades',                            'ra': 66.75,  'dec': 15.87,  'type': 'amas ouvert'},
    {'nom': "Nébuleuse de l'Aigle (M16)",        'ra': 274.70, 'dec': -13.79, 'type': 'nébuleuse'},
    {'nom': 'Amas Globulaire M22',               'ra': 279.10, 'dec': -23.90, 'type': 'amas globulaire'},
    {'nom': 'Nébuleuse Oméga (M17)',             'ra': 275.20, 'dec': -16.18, 'type': 'nébuleuse'},
]
# Nettoyer les entrées valides uniquement
DSO_CATALOG = [o for o in DSO_CATALOG if 'ra' in o and 'dec' in o and 'nom' in o]


def _condition(alt_deg, moon_pct):
    """Qualité d'observation selon altitude et pollution lunaire."""
    if alt_deg > 60:
        base = 'Excellent'
    elif alt_deg > 40:
        base = 'Très bon'
    elif alt_deg > 20:
        base = 'Bon'
    else:
        base = 'Passable'
    if moon_pct > 80:
        return base + ' (Lune gênante)'
    if moon_pct > 50:
        return base + ' (Lune présente)'
    return base


def get_moon_phase():
    """Phase lunaire précise via astropy (élongation écliptique réelle)."""
    try:
        now = Time.now()
        moon = get_body('moon', now)
        sun  = get_body('sun',  now)
        moon_ecl = moon.transform_to(GeocentricMeanEcliptic(equinox=now))
        sun_ecl  = sun.transform_to(GeocentricMeanEcliptic(equinox=now))
        phase_angle = (moon_ecl.lon.deg - sun_ecl.lon.deg) % 360.0
        illumination = round((1.0 - math.cos(math.radians(phase_angle))) / 2.0 * 100.0)
        cycle_day = round(phase_angle / 360.0 * 29.53, 1)
        if phase_angle < 6.1:    phase = 'Nouvelle Lune 🌑'
        elif phase_angle < 83.0: phase = 'Premier Croissant 🌒'
        elif phase_angle < 96.0: phase = 'Premier Quartier 🌓'
        elif phase_angle < 173:  phase = 'Gibbeuse Croissante 🌔'
        elif phase_angle < 187:  phase = 'Pleine Lune 🌕'
        elif phase_angle < 264:  phase = 'Gibbeuse Décroissante 🌖'
        elif phase_angle < 277:  phase = 'Dernier Quartier 🌗'
        else:                    phase = 'Dernier Croissant 🌘'
        return {'phase': phase, 'illumination_pct': illumination, 'cycle_jour': cycle_day}
    except Exception:
        # Fallback approximatif si astropy échoue
        now_dt = datetime.utcnow()
        known_new = datetime(2024, 1, 11)
        delta = (now_dt - known_new).days
        cycle = delta % 29.53
        phase_pct = round((cycle / 29.53) * 100)
        if cycle < 1:    phase = 'Nouvelle Lune 🌑'
        elif cycle < 7:  phase = 'Premier Croissant 🌒'
        elif cycle < 9:  phase = 'Premier Quartier 🌓'
        elif cycle < 14: phase = 'Gibbeuse Croissante 🌔'
        elif cycle < 16: phase = 'Pleine Lune 🌕'
        elif cycle < 22: phase = 'Gibbeuse Décroissante 🌖'
        elif cycle < 24: phase = 'Dernier Quartier 🌗'
        else:            phase = 'Dernier Croissant 🌘'
        return {'phase': phase, 'illumination_pct': phase_pct, 'cycle_jour': round(cycle, 1)}


def get_tonight_objects():
    """Objets célestes visibles depuis Tlemcen maintenant, calculés par astropy."""
    moon = get_moon_phase()
    now_dt = datetime.now(timezone.utc)
    objects = []
    source = 'astropy/éphémérides réelles'

    try:
        now = Time.now()
        frame = AltAz(obstime=now, location=LOCATION)
        moon_pct = moon.get('illumination_pct', 50)

        for obj in DSO_CATALOG:
            coord = SkyCoord(ra=obj['ra'] * u.deg, dec=obj['dec'] * u.deg, frame='icrs')
            altaz = coord.transform_to(frame)
            alt_deg = float(altaz.alt.deg)
            az_deg  = float(altaz.az.deg)
            if alt_deg > 15.0:
                objects.append({
                    'nom':       obj['nom'],
                    'type':      obj['type'],
                    'altitude':  f'{alt_deg:.0f}°',
                    'azimut':    f'{az_deg:.0f}°',
                    'condition': _condition(alt_deg, moon_pct),
                })

        # Top 6 par altitude décroissante
        objects.sort(key=lambda x: -float(x['altitude'].rstrip('°')))
        objects = objects[:6]

    except Exception:
        source = 'fallback/saison (astropy indisponible)'
        month = now_dt.month
        if month in [11, 12, 1, 2, 3]:
            objects = [
                {'nom': 'Orion (M42)',      'altitude': '~70°', 'condition': 'Excellent', 'type': 'nébuleuse'},
                {'nom': 'Pléiades (M45)',   'altitude': '~65°', 'condition': 'Excellent', 'type': 'amas ouvert'},
                {'nom': 'Taureau (M1)',     'altitude': '~60°', 'condition': 'Bon',       'type': 'nébuleuse'},
            ]
        elif month in [3, 4, 5, 6]:
            objects = [
                {'nom': 'Grande Ourse (M81)', 'altitude': '~50°', 'condition': 'Excellent', 'type': 'galaxie'},
                {'nom': 'Vierge (M104)',       'altitude': '~45°', 'condition': 'Bon',       'type': 'galaxie'},
            ]
        elif month in [6, 7, 8, 9]:
            objects = [
                {'nom': "Amas d'Hercule (M13)", 'altitude': '~65°', 'condition': 'Excellent', 'type': 'amas globulaire'},
                {'nom': 'Cygne (NGC 7000)',      'altitude': '~70°', 'condition': 'Excellent', 'type': 'nébuleuse'},
            ]
        else:
            objects = [
                {'nom': "Andromède (M31)",    'altitude': '~60°', 'condition': 'Excellent', 'type': 'galaxie'},
                {'nom': 'Double Amas Persée', 'altitude': '~65°', 'condition': 'Excellent', 'type': 'amas ouvert'},
            ]

    return {
        'date':   now_dt.strftime('%d/%m/%Y'),
        'heure':  now_dt.strftime('%H:%M UTC'),
        'lune':   moon,
        'objets': objects,
        'lieu':   'Tlemcen, Algérie (34.88°N, 1.32°E)',
        'source': source,
    }
