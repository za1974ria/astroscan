"""Service iss_live — récupération position ISS en direct (sans cache).

Extrait depuis station_web.py L2768-L2811 (+ helpers L1739, L3008) lors de
PASS 23. Helpers internes (_curl_get, _guess_region) copiés verbatim pour
éviter tout import retour vers station_web (anti-circulaire).

station_web.py conserve un alias re-export pour la compat des imports legacy.
"""
import logging
import subprocess

from services.utils import _safe_json_loads

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
