"""Service iss_live — récupération position ISS en direct (sans cache).

Extrait depuis station_web.py L2768-L2811 (+ helpers L1739, L3008) lors de
PASS 23. Helpers internes (_curl_get, _guess_region) copiés verbatim pour
éviter tout import retour vers station_web (anti-circulaire).

PASS 27.13 (2026-05-09) — Ajout de 2 helpers crew :
    _fetch_iss_crew() -> int           # raw HTTP open-notify (cache layer above)
    _get_iss_crew() -> int             # cached 5 min, sanity bounds [1, 20], default 7

station_web.py conserve un alias re-export pour la compat des imports legacy.
"""
import json
import logging
import subprocess

from services.utils import _safe_json_loads
from services.cache_service import get_cached

log = logging.getLogger(__name__)


def _curl_get(url, timeout=15):
    """GET via curl — contourne restrictions réseau urllib (Tlemcen).

    Copie verbatim depuis station_web.py L1739 lors de PASS 23.
    """
    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '--max-time', str(timeout),
             '-H', 'User-Agent: ORBITAL-CHOHRA/1.0', url],
            capture_output=True, text=True, timeout=timeout + 2
        )
        return (r.stdout or "").strip()
    except Exception as e:
        log.warning(f"curl_get {url[:60]}: {e}")
        return ""


def _guess_region(lat, lon):
    """Estimation grossière de la région survolée.

    Copie verbatim depuis station_web.py L3008 lors de PASS 23.
    """
    if -60 < lat < 60:
        if -30 < lon < 60:
            return 'Afrique / Europe'
        elif 60 < lon < 150:
            return 'Asie'
        elif -150 < lon < -30:
            return 'Amériques'
        else:
            return 'Océan Pacifique'
    elif lat >= 60:
        return 'Arctique'
    else:
        return 'Antarctique'


def _fetch_iss_live():
    """Récupère une position ISS fiable via whereTheISS / open-notify (sans cache).

    Copie verbatim depuis station_web.py L2768 lors de PASS 23.
    """
    urls = [
        'https://api.wheretheiss.at/v1/satellites/25544',
        'http://api.open-notify.org/iss-now.json',
    ]
    for url in urls:
        raw = _curl_get(url, timeout=8)
        if not raw:
            continue
        try:
            data = _safe_json_loads(raw, "iss_live")
            if not isinstance(data, dict):
                continue
            # whereTheISS.at format
            if 'latitude' in data:
                lat = float(data['latitude'])
                lon = float(data['longitude'])
                alt = float(data.get('altitude', 408.0))
                speed = float(data.get('velocity', 27600.0))
                region = data.get('country_name', _guess_region(lat, lon))
            # open-notify format
            elif 'iss_position' in data:
                pos = data['iss_position']
                lat = float(pos['latitude'])
                lon = float(pos['longitude'])
                alt = 408.0
                speed = 27600.0
                region = _guess_region(lat, lon)
            else:
                continue

            return {
                'ok': True,
                'lat': lat,
                'lon': lon,
                'alt': round(alt, 1),
                'speed': round(speed, 0),
                'region': region,
            }
        except Exception as e:
            log.warning(f"ISS {url}: {e}")
            continue
    return None


def _fetch_iss_crew():
    """Lecture brute du nombre d'astronautes à bord de l'ISS via open-notify."""
    raw = _curl_get('http://api.open-notify.org/astros.json', timeout=6)
    if not raw:
        return 7
    try:
        data = json.loads(raw)
        iss = [p for p in data.get('people', []) if p.get('craft') == 'ISS']
        return len(iss) if iss else data.get('number', 7)
    except Exception:
        return 7


def _get_iss_crew():
    """
    Nombre d'astronautes à bord de l'ISS avec cache serveur 5 min.
    On interroge la source officielle une seule fois toutes les 5 minutes,
    puis PC et Android partagent la même valeur.
    """
    crew = get_cached('iss_crew', 300, _fetch_iss_crew)
    try:
        crew = int(crew)
        if crew <= 0 or crew > 20:
            crew = 7
    except Exception:
        crew = 7
    return crew
