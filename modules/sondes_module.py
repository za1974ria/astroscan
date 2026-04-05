# -*- coding: utf-8 -*-
"""
Module SONDES SPATIALES — agrégation pour /api/sondes.
Retourne voyager1, voyager2, iss, perseverance, curiosity, jwst, hubble, parker.
Utilise curl (subprocess) pour contourner les restrictions réseau.
"""

import os
import json
import subprocess
from datetime import datetime, timezone

STATION = os.environ.get('STATION', '/root/astro_scan')


def _curl(url, timeout=10, extra_args=None):
    try:
        cmd = ['curl', '-s', '--max-time', str(timeout)]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(url)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5, cwd=STATION)
        return (r.stdout or '').strip()
    except Exception:
        return ''


def _curl_get(url, timeout=15):
    """GET via curl — contourne restrictions urllib."""
    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '--max-time', str(timeout),
             '-H', 'User-Agent: ORBITAL-CHOHRA/1.0', url],
            capture_output=True, text=True, timeout=timeout + 2,
            cwd=STATION,
        )
        return r.stdout
    except Exception:
        return None


def _fetch_voyager_jpl():
    """Voyager 1 & 2 — JPL Horizons via orbit_engine.get_voyager_precise."""
    try:
        from modules.orbit_engine import get_voyager_precise
        return {
            'voyager1': get_voyager_precise(1),
            'voyager2': get_voyager_precise(2),
        }
    except Exception:
        return {}


def _fetch_iss():
    try:
        import math
        from modules.orbit_engine import get_iss_precise, get_iss_crew
        data = get_iss_precise()
        if 'error' not in data:
            crew = get_iss_crew()
            crew_display = crew if crew else []
            crew_count = len(crew) if crew else 7
            result = {
                'name': 'ISS',
                'status': 'En orbite',
                'lat': round(data['lat'], 4),
                'lon': round(data['lon'], 4),
                'altitude_km': round(data['alt_km'], 1),
                'speed_kms': round(data.get('speed_kms', 7.66), 2),
                'crew_count': crew_count,
                'crew': crew_display,
                'source': 'Skyfield/SGP4'
            }
            # Sanitise NaN/Inf
            for k, v in result.items():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    result[k] = 0.0
            return {'iss': result}
    except Exception:
        pass
    return {'iss': {'name': 'ISS', 'lat': 0, 'lon': 0, 'altitude_km': 408, 'speed_kms': 7.66, 'crew_count': 7, 'crew': [], 'status': 'En orbite', 'source': 'fallback'}}


def _fetch_mars_rover(rover='perseverance'):
    NASA_KEY = os.environ.get('NASA_API_KEY', 'DEMO_KEY').strip()

    # Source 1 : API NASA Mars (timeout long)
    raw = _curl(f'https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/latest_photos?api_key={NASA_KEY}&page=1', timeout=25, extra_args=['--ipv4'])
    if raw:
        try:
            data = json.loads(raw)
            photos = data.get('latest_photos', [])
            if photos:
                p = photos[0]
                return {
                    'name': rover.capitalize(),
                    'status': 'ACTIF — SOL ' + str(p.get('sol', 0)),
                    'sol': p.get('sol', 0),
                    'earth_date': p.get('earth_date', ''),
                    'camera': p.get('camera', {}).get('full_name', ''),
                    'img_url': p.get('img_src', ''),
                    'total_photos': len(photos),
                    'source': 'NASA API'
                }
        except Exception:
            pass

    # Source 2 : APOD fallback avec image Mars
    raw2 = _curl(f'https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}&date=2026-03-14', timeout=10, extra_args=['--ipv4'])
    if raw2:
        try:
            data = json.loads(raw2)
            if isinstance(data, list):
                data = data[0]
            return {
                'name': rover.capitalize(),
                'status': 'DONNÉES NASA APOD',
                'earth_date': data.get('date', ''),
                'img_url': data.get('url', ''),
                'camera': 'NASA APOD',
                'source': 'APOD fallback'
            }
        except Exception:
            pass

    return {'name': rover.capitalize(), 'status': 'Indisponible'}


def _fetch_mars_rovers():
    """Perseverance & Curiosity — agrégation."""
    return {
        'perseverance': _fetch_mars_rover('perseverance'),
        'curiosity': _fetch_mars_rover('curiosity'),
    }


def _static_sondes():
    """JWST, Hubble, Parker — données statiques."""
    return {
        'jwst': {
            'name': 'James Webb Space Telescope',
            'status': 'L2',
            'position': 'Point de Lagrange L2',
            'mission': 'Infrarouge',
        },
        'hubble': {
            'name': 'Hubble',
            'status': 'LEO',
            'altitude_km': 547,
            'mission': 'Optique / UV',
        },
        'parker': {
            'name': 'Parker Solar Probe',
            'status': 'En vol',
            'mission': 'Vent solaire',
        },
    }


def get_sondes_payload():
    """
    Agrège toutes les sondes pour /api/sondes.
    Clés : voyager1, voyager2, iss, perseverance, curiosity, jwst, hubble, parker, generated_at.
    """
    payload = {}
    payload.update(_fetch_voyager_jpl())
    payload.update(_fetch_iss())
    payload.update(_fetch_mars_rovers())
    payload.update(_static_sondes())
    payload['generated_at'] = datetime.now(timezone.utc).isoformat()
    return payload
