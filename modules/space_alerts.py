import subprocess, json

def _curl(url, timeout=10):
    try:
        r = subprocess.run(['curl','-s','--ipv4','--max-time',str(timeout),url], capture_output=True, text=True)
        return (r.stdout or '').strip()
    except Exception:
        return ''

def get_asteroid_alerts():
    try:
        from datetime import datetime
        today = datetime.utcnow().strftime('%Y-%m-%d')
        import os
        key = os.environ.get('NASA_API_KEY','DEMO_KEY').strip()
        raw = _curl(f'https://api.nasa.gov/neo/rest/v1/feed?start_date={today}&end_date={today}&api_key={key}', timeout=15)
        if not raw:
            return {'alerts': [], 'error': 'no data', 'total_today': 0}
        data = json.loads(raw)
        alerts = []
        for date, neos in data.get('near_earth_objects',{}).items():
            for neo in neos:
                if neo.get('is_potentially_hazardous_asteroid'):
                    approach = neo['close_approach_data'][0] if neo.get('close_approach_data') else {}
                    miss = approach.get('miss_distance') or {}
                    vel = approach.get('relative_velocity') or {}
                    alerts.append({
                        'name': neo.get('name','?'),
                        'hazardous': True,
                        'diameter_m': round(neo.get('estimated_diameter',{}).get('meters',{}).get('estimated_diameter_max',0)),
                        'distance_km': round(float(miss.get('kilometers',0) or 0)),
                        'velocity_kms': round(float(vel.get('kilometers_per_second',0) or 0), 2),
                        'date': approach.get('close_approach_date','')
                    })
        return {'alerts': alerts, 'total_today': data.get('element_count',0), 'source': 'NASA NeoWs'}
    except Exception as e:
        return {'alerts': [], 'error': str(e), 'total_today': 0}

def get_solar_weather():
    try:
        raw = _curl('https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json', timeout=10)
        if not raw:
            return {}
        data = json.loads(raw)
        if len(data) > 1:
            latest = data[-1]
            speed = float(latest[2] or 0)
            return {
                'density': round(float(latest[1] or 0), 2),
                'speed_kms': round(speed, 1),
                'temperature': round(float(latest[3] or 0)),
                'source': 'NOAA SWPC',
                'status': 'TEMPÊTE' if speed > 500 else 'NORMALE'
            }
    except Exception as e:
        return {'error': str(e)}
    return {}

def get_space_debris():
    try:
        raw = _curl('https://celestrak.org/SOCRATES/query.php?CODE=ALL&ORDER=5&MAX=5&FORMAT=JSON', timeout=10)
        if not raw:
            return {'debris': [], 'note': 'Indisponible'}
        data = json.loads(raw)
        return {'debris': data[:5] if isinstance(data, list) else [], 'source': 'Celestrak SOCRATES'}
    except Exception:
        return {'debris': [], 'note': 'Indisponible'}
