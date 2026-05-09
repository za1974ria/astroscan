
import math
import datetime
import os
import requests

# Tlemcen (Algérie) — longitude **est** positive (~1,32° E). Une valeur négative plaçait l’observateur en mer.
LAT, LON = 34.87, 1.32
TLE_URL = "https://celestrak.org/satcat/tle.php?CATNR=25544"


def _iss_tle_from_local_active():
    """Extrait le bloc NORAD 25544 depuis data/tle/active.tle (même fichier que le reste d’AstroScan)."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(base, "..", "data", "tle", "active.tle"))
    if not os.path.isfile(path):
        return None, None, None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except Exception:
        return None, None, None
    for i, line in enumerate(lines):
        if not line.startswith("1 25544"):
            continue
        tle1 = line
        tle2 = lines[i + 1] if i + 1 < len(lines) else ""
        if not tle2.startswith("2 25544"):
            continue
        name = lines[i - 1] if i > 0 else "ISS"
        return name, tle1, tle2
    return None, None, None


def fetch_iss_tle():
    """Priorité au TLE local (déjà maintenu par AstroScan) pour éviter blocage si Celestrak est lent."""
    loc = _iss_tle_from_local_active()
    if loc[1] and loc[2]:
        return loc
    try:
        r = requests.get(TLE_URL, timeout=8)
        lines = [l.strip() for l in r.text.strip().splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if line.startswith("1 25544"):
                return lines[i - 1] if i > 0 else "ISS", line, lines[i + 1]
    except Exception as e:
        print(f"[TLE] {e}")
    return None, None, None

def _elevation(r, lat, lon):
    Re = 6371.0
    rx,ry,rz = r
    ox = Re*math.cos(lat)*math.cos(lon)
    oy = Re*math.cos(lat)*math.sin(lon)
    oz = Re*math.sin(lat)
    dx,dy,dz = rx-ox,ry-oy,rz-oz
    d = math.sqrt(dx**2+dy**2+dz**2)
    nx=math.cos(lat)*math.cos(lon); ny=math.cos(lat)*math.sin(lon); nz=math.sin(lat)
    dot=(dx*nx+dy*ny+dz*nz)/d
    return math.degrees(math.asin(max(-1,min(1,dot))))

def get_next_passes():
    try:
        from sgp4.api import Satrec, jday
    except:
        return {"error":"sgp4 manquant","passes":[]}
    name,tle1,tle2 = fetch_iss_tle()
    if not tle1:
        return {"error":"TLE indisponible","passes":[]}
    sat = Satrec.twoline2rv(tle1, tle2)
    lat,lon = math.radians(LAT),math.radians(LON)
    now = datetime.datetime.now(datetime.timezone.utc)
    passes=[]; in_pass=False; pass_start=None; pass_max=0; pass_max_t=None
    for i in range(int(2*86400/30)):
        t = now + datetime.timedelta(seconds=i*30)
        jd,fr = jday(t.year,t.month,t.day,t.hour,t.minute,t.second)
        e,r,v = sat.sgp4(jd,fr)
        if e!=0: continue
        el = _elevation(r, lat, lon)
        if el >= 10:
            if not in_pass:
                in_pass=True; pass_start=t; pass_max=el; pass_max_t=t
            elif el>pass_max:
                pass_max=el; pass_max_t=t
        else:
            if in_pass:
                in_pass=False
                passes.append({"rise_time":pass_start.strftime("%Y-%m-%d %H:%M UTC"),"max_elevation":round(pass_max,1),"set_time":t.strftime("%H:%M UTC"),"duration_sec":int((t-pass_start).total_seconds()),"visible":pass_max>20})
                if len(passes)>=6: break
    return {"location": "Tlemcen 34.87°N, 1.32°E", "source": "Celestrak+SGP4", "passes": passes}


def get_next_passes_observatoire_list():
    """
    Même calcul que get_next_passes(), format liste attendu par l’Observatoire
    (open-notify) : [{ risetime: unix_s, duration: secondes }, ...].
    """
    data = get_next_passes()
    if not isinstance(data, dict) or data.get("error"):
        return []
    out = []
    for p in data.get("passes") or []:
        try:
            rt_s = (p.get("rise_time") or "").strip()
            t = datetime.datetime.strptime(rt_s, "%Y-%m-%d %H:%M UTC").replace(tzinfo=datetime.timezone.utc)
            risetime = int(t.timestamp())
            dur = int(p.get("duration_sec") or 0)
            if risetime > 0 and dur >= 0:
                out.append({"risetime": risetime, "duration": dur})
        except Exception:
            continue
    return out
