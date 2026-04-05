import subprocess, json, os

def _curl(url, timeout=10):
    try:
        r = subprocess.run(['curl','-s','--ipv4','--max-time',str(timeout), url], capture_output=True, text=True)
        return (r.stdout or '').strip()
    except Exception:
        return ''

NASA_KEY = os.environ.get('NASA_API_KEY','DEMO_KEY').strip()

# ═══ HUBBLE ═══
def get_hubble_images():
    # Source 1: NASA APOD avec tag hubble
    raw = _curl(f'https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}&count=6', timeout=10)
    if raw:
        try:
            items = json.loads(raw)
            return [{'title': i.get('title','Hubble'), 'url': i.get('hdurl', i.get('url','')), 'date': i.get('date',''), 'explanation': (i.get('explanation') or '')[:200]} for i in items if i.get('url')]
        except Exception:
            pass
    return []

# ═══ JWST ═══
def get_jwst_images():
    raw = _curl(f'https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}&count=6&thumbs=true', timeout=10)
    if raw:
        try:
            items = json.loads(raw)
            return [{'title': i.get('title','JWST'), 'url': i.get('hdurl', i.get('url','')), 'date': i.get('date',''), 'explanation': (i.get('explanation') or '')[:200]} for i in items if i.get('url')]
        except Exception:
            pass
    return []

# ═══ SPACEX ═══
def get_spacex_launches():
    # Source 1 : RocketLaunch.Live (free, fresh data)
    raw = _curl('https://fdo.rocketlaunch.live/json/launches/next/5', timeout=10)
    if raw:
        try:
            data = json.loads(raw)
            launches = data.get('result', [])
            if launches:
                results = []
                for l in launches[:6]:
                    win = l.get('win_open') or l.get('t0') or ''
                    date = win[:10] if win else ''
                    vehicle = (l.get('vehicle') or {}).get('name', '')
                    provider = (l.get('provider') or {}).get('name', '')
                    name = l.get('name') or (provider + ' — ' + vehicle)
                    pad = (l.get('pad') or {}).get('name', '')
                    results.append({
                        'name': name,
                        'date': date,
                        'rocket': vehicle,
                        'details': (pad or provider or 'Lancement spatial')[:150],
                        'success': None,
                        'upcoming': True,
                    })
                return results
        except Exception:
            pass
    # Source 2 : LL2 (Launch Library 2 — open data)
    raw2 = _curl('https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=5&format=json', timeout=12)
    if raw2:
        try:
            data2 = json.loads(raw2)
            launches2 = data2.get('results', [])
            results2 = []
            for l in launches2[:6]:
                results2.append({
                    'name': l.get('name', ''),
                    'date': (l.get('net') or '')[:10],
                    'rocket': (l.get('rocket') or {}).get('configuration', {}).get('name', ''),
                    'details': (l.get('mission') or {}).get('description', 'Mission spatiale')[:150] or 'Mission spatiale',
                    'success': None,
                    'upcoming': True,
                })
            if results2:
                return results2
        except Exception:
            pass
    return []

# ═══ SYSTÈME SOLAIRE POSITIONS ═══
def get_solar_system_positions():
    planets = {
        'mars': '499', 'venus': '299', 'jupiter': '599',
        'saturn': '699', 'mercury': '199'
    }
    result = {}
    for name, id in planets.items():
        raw = _curl(f'https://ssd.jpl.nasa.gov/api/horizons.api?format=json&COMMAND={id}&OBJ_DATA=YES&MAKE_EPHEM=NO', timeout=8)
        if raw:
            try:
                data = json.loads(raw)
                result[name] = {'name': name.capitalize(), 'data': (data.get('result') or '')[:200], 'source': 'JPL'}
            except Exception:
                pass
    return result

# ═══ SPACE NEWS ═══
def get_space_news():
    raw = _curl('https://api.spaceflightnewsapi.net/v4/articles/?limit=8&format=json', timeout=10)
    if raw:
        try:
            data = json.loads(raw)
            articles = data.get('results', data if isinstance(data, list) else [])
            return [{'title': a.get('title',''), 'url': a.get('url',''), 'image': a.get('image_url',''), 'summary': (a.get('summary') or '')[:150], 'published': a.get('published_at','')} for a in (articles[:8] if isinstance(articles, list) else [])]
        except Exception:
            pass
    return []

# ═══ ISS PASSES TLEMCEN ═══
def get_iss_passes_tlemcen():
    """
    Passages visibles depuis Tlemcen (~34,88°N, 1,32°E).
    1) Calcul local TLE + SGP4 (rapide, même jeu de données qu’AstroScan).
    2) open-notify si le calcul local ne renvoie rien et que l’API répond.
    """
    tlem_lat, tlem_lon = 34.88, 1.32

    def _normalize_open_notify_response(resp_list):
        out = []
        if not isinstance(resp_list, list):
            return out
        for item in resp_list:
            if not isinstance(item, dict):
                continue
            rt = item.get("risetime")
            dur = item.get("duration")
            if rt is None or dur is None:
                continue
            try:
                out.append({"risetime": int(rt), "duration": int(dur)})
            except (TypeError, ValueError):
                continue
        return out

    try:
        from modules.iss_passes import get_next_passes_observatoire_list
        local_list = get_next_passes_observatoire_list()
        if local_list:
            return local_list
    except Exception:
        pass

    for base in ("http://api.open-notify.org", "https://api.open-notify.org"):
        url = "{0}/iss-pass.json?lat={1}&lon={2}&n=5".format(base, tlem_lat, tlem_lon)
        raw = _curl(url, timeout=8)
        if not raw or raw.lstrip().startswith("<"):
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if (data.get("message") or "").lower() != "success":
            continue
        normalized = _normalize_open_notify_response(data.get("response"))
        if normalized:
            return normalized
    return []

# ═══ MARS WEATHER ═══
def get_mars_weather():
    raw = _curl(f'https://api.nasa.gov/insight_weather/?api_key={NASA_KEY}&feedtype=json&ver=1.0', timeout=10)
    if raw:
        try:
            data = json.loads(raw)
            sols = data.get('sol_keys', [])
            if sols:
                latest = data.get(sols[-1], {})
                return {
                    'sol': sols[-1],
                    'temp_max': latest.get('AT', {}).get('mx', '?'),
                    'temp_min': latest.get('AT', {}).get('mn', '?'),
                    'pressure': latest.get('PRE', {}).get('av', '?'),
                    'source': 'NASA InSight'
                }
        except Exception:
            pass
    return {'sol': '?', 'source': 'Indisponible'}
