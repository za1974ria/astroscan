import subprocess, json
from skyfield.api import load, EarthSatellite, wgs84

def _curl(url, timeout=10):
    try:
        r = subprocess.run(['curl', '-s', '--ipv4', '--max-time', str(timeout), url], capture_output=True, text=True)
        return (r.stdout or '').strip()
    except Exception:
        return ''

_iss_precise_cache = {'data': None, 'ts': 0}

def _load_local_iss_tle():
    """Charge le TLE ISS depuis le fichier local data/tle/active.tle."""
    import os, time as _t
    paths = [
        '/root/astro_scan/data/tle/active.tle',
        '/root/astro_scan/data/noaa_tle.json',
    ]
    for path in paths:
        if not os.path.exists(path):
            continue
        age = _t.time() - os.path.getmtime(path)
        if age > 7200:  # TLE > 2h — trop vieux
            continue
        try:
            text = open(path).read()
            for chunk in text.split('\n\n'):
                lines = [l.strip() for l in chunk.strip().split('\n') if l.strip()]
                if len(lines) >= 3 and '25544' in lines[1] and lines[1].startswith('1 ') and lines[2].startswith('2 '):
                    return '\n'.join(lines[:3])
            # Chercher ISS n'importe où dans le fichier
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for i, l in enumerate(lines):
                if l.startswith('1 25544'):
                    if i > 0 and i + 1 < len(lines):
                        return '\n'.join([lines[i-1], lines[i], lines[i+1]])
        except Exception:
            pass
    return ''

def get_iss_precise():
    import time as _t
    # Cache 30s — ISS bouge peu sur 30s
    if _iss_precise_cache['data'] and (_t.time() - _iss_precise_cache['ts']) < 30:
        return _iss_precise_cache['data']
    try:
        ts = load.timescale()
        t = ts.now()

        # Source 1 : TLE local (immédiat, pas de réseau)
        tle_raw = _load_local_iss_tle()

        # Source 2 : wheretheiss.at (rapide ~0.5s) si pas de TLE local
        if not tle_raw:
            raw = _curl('https://api.wheretheiss.at/v1/satellites/25544', timeout=5)
            if raw:
                import json as _json
                d = _json.loads(raw)
                result = {
                    'lat': round(float(d['latitude']), 4),
                    'lon': round(float(d['longitude']), 4),
                    'alt_km': round(float(d['altitude']), 1),
                    'speed_kms': round(float(d['velocity']) / 3600, 2),
                    'source': 'wheretheiss.at'
                }
                _iss_precise_cache['data'] = result
                _iss_precise_cache['ts'] = _t.time()
                return result

        # Source 3 : CelesTrak (fallback réseau, timeout court)
        if not tle_raw:
            tle_raw = _curl('https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE', timeout=5)

        if not tle_raw:
            return {'error': 'Toutes sources TLE échouées'}

        lines = [l.strip() for l in tle_raw.split('\n') if l.strip()]
        name, l1, l2 = lines[0], lines[1], lines[2]
        sat = EarthSatellite(l1, l2)
        geo = sat.at(t)
        subpoint = wgs84.subpoint(geo)
        import math
        vel = geo.velocity.km_per_s
        speed = round(math.sqrt(sum(v**2 for v in vel)), 2)
        lat = float(subpoint.latitude.degrees)
        lon = float(subpoint.longitude.degrees)
        alt = float(subpoint.elevation.km)
        if math.isnan(lat) or math.isnan(alt):
            return {'error': 'NaN'}
        result = {
            'lat': round(lat, 4),
            'lon': round(lon, 4),
            'alt_km': round(alt, 1),
            'speed_kms': speed,
            'source': 'Skyfield/SGP4'
        }
        _iss_precise_cache['data'] = result
        _iss_precise_cache['ts'] = _t.time()
        return result
    except Exception as e:
        return {'error': str(e)}

_iss_crew_cache = {'data': [], 'ts': 0}

def get_iss_crew():
    import time
    # Cache 1h — évite les appels externes bloquants sur chaque requête
    if _iss_crew_cache['data'] and (time.time() - _iss_crew_cache['ts']) < 3600:
        return _iss_crew_cache['data']

    # Source 1 : open-notify officiel (timeout court)
    try:
        raw = _curl('http://api.open-notify.org/astros.json', timeout=4)
        if raw:
            import json as _j
            data = _j.loads(raw)
            crew = [p['name'] for p in data.get('people', []) if p.get('craft') == 'ISS']
            if crew:
                _iss_crew_cache['data'] = crew
                _iss_crew_cache['ts'] = time.time()
                return crew
    except Exception:
        pass

    # Source 2 : lldev.thespacedevs.com (Launch Library 2, plus fiable)
    try:
        raw = _curl('https://lldev.thespacedevs.com/2.2.0/expedition/?ordering=-start&limit=1&format=json', timeout=5)
        if raw:
            import json as _j
            data = _j.loads(raw)
            results = data.get('results', [])
            if results:
                crew_count = results[0].get('crew', [])
                names = [c.get('astronaut', {}).get('name', 'Astronaute') for c in crew_count[:9]]
                if names:
                    _iss_crew_cache['data'] = names
                    _iss_crew_cache['ts'] = time.time()
                    return names
    except Exception:
        pass

    # Fallback statique — équipage connu (Expédition 72)
    fallback = ['Équipage ISS — 7 membres (données en cache)']
    _iss_crew_cache['data'] = fallback
    _iss_crew_cache['ts'] = time.time()
    return fallback


def get_voyager_precise(num=1):
    """Voyager 1 (num=1) ou 2 (num=2) — JPL Horizons, fallback calcul approx."""
    import math
    cmd = '%2D31' if num == 1 else '%2D32'
    url = (
        f'https://ssd.jpl.nasa.gov/api/horizons.api?format=json&COMMAND={cmd}&OBJ_DATA=NO'
        f'&MAKE_EPHEM=YES&EPHEM_TYPE=VECTORS&CENTER=500@10'
        f'&START_TIME=2026-03-14&STOP_TIME=2026-03-15&STEP_SIZE=1d&VEC_TABLE=3'
    )
    raw = _curl(url, timeout=15)
    if raw:
        try:
            data = json.loads(raw)
            result = data.get('result', '')
            if isinstance(result, dict):
                result = result.get('__content__', result) if hasattr(result, 'get') else str(result)
            for line in (result if isinstance(result, str) else '').split('\n'):
                line = line.strip()
                if line.startswith('X =') or 'X=' in line:
                    parts = line.replace('=', ' ').split()
                    for i, p in enumerate(parts):
                        if p == 'X' and i + 5 < len(parts):
                            try:
                                x = float(parts[i + 1])
                                y = float(parts[i + 3])
                                z = float(parts[i + 5])
                                au = math.sqrt(x**2 + y**2 + z**2) / 1.496e8
                                return {
                                    'name': 'Voyager 1' if num == 1 else 'Voyager 2',
                                    'distance_au': round(au, 2),
                                    'distance_km': int(au * 149597870.7),
                                    'speed_kms': 17.0 if num == 1 else 15.4,
                                    'status': 'OPÉRATIONNELLE',
                                    'source': 'JPL Horizons',
                                }
                            except (ValueError, IndexError):
                                break
                        if 'X' in p and i + 1 < len(parts):
                            try:
                                x = float(parts[i + 1])
                                y = float(parts[i + 2]) if i + 2 < len(parts) else 0
                                z = float(parts[i + 3]) if i + 3 < len(parts) else 0
                                au = math.sqrt(x**2 + y**2 + z**2) / 1.496e8
                                return {
                                    'name': 'Voyager 1' if num == 1 else 'Voyager 2',
                                    'distance_au': round(au, 2),
                                    'distance_km': int(au * 149597870.7),
                                    'speed_kms': 17.0 if num == 1 else 15.4,
                                    'status': 'OPÉRATIONNELLE',
                                    'source': 'JPL Horizons',
                                }
                            except (ValueError, IndexError):
                                break
        except Exception:
            pass
    # Fallback approx
    import time
    days = (time.time() - (536457600 if num == 1 else 543196800)) / 86400
    au = 163.0 + days * 0.000317 if num == 1 else 135.0 + days * 0.000263
    return {
        'name': 'Voyager 1' if num == 1 else 'Voyager 2',
        'distance_au': round(au, 2),
        'distance_km': int(au * 149597870.7),
        'speed_kms': 17.0 if num == 1 else 15.4,
        'status': 'OPÉRATIONNELLE',
        'source': 'Calcul approx.',
    }
