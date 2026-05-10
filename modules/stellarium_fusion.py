import ephem, datetime, math, json, os

from app.constants.observatory import OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M
LAT, LON, ALT = str(OBSERVER_LAT), str(OBSERVER_LON), OBSERVER_ALT_M

def get_observer():
    obs = ephem.Observer()
    obs.lat = LAT; obs.lon = LON; obs.elevation = ALT
    obs.date = datetime.datetime.now(datetime.timezone.utc)
    obs.pressure = 0  # pas de réfraction atmosphérique
    return obs

MESSIER = [
    ("M1","Nébuleuse du Crabe","Nébuleuse","Taureau",ephem.readdb("M1,f|N,5:34:32,22:00:52,8.4")),
    ("M13","Amas d Hercule","Amas globulaire","Hercule",ephem.readdb("M13,f|C,16:41:41,36:27:37,5.8")),
    ("M31","Galaxie d Andromède","Galaxie","Andromède",ephem.readdb("M31,f|G,0:42:44,41:16:09,3.4")),
    ("M42","Nébuleuse d Orion","Nébuleuse","Orion",ephem.readdb("M42,f|N,5:35:17,-5:23:28,4.0")),
    ("M45","Pléiades","Amas ouvert","Taureau",ephem.readdb("M45,f|C,3:47:00,24:07:00,1.6")),
    ("M51","Galaxie du Tourbillon","Galaxie","Chiens de Chasse",ephem.readdb("M51,f|G,13:29:52,47:11:43,8.4")),
    ("M57","Nébuleuse de la Lyre","Nébuleuse planétaire","Lyre",ephem.readdb("M57,f|N,18:53:35,33:01:45,8.8")),
    ("M63","Galaxie du Tournesol","Galaxie","Chiens de Chasse",ephem.readdb("M63,f|G,13:15:49,42:01:45,8.6")),
    ("M81","Galaxie de Bode","Galaxie","Grande Ourse",ephem.readdb("M81,f|G,9:55:33,69:03:55,6.9")),
    ("M82","Galaxie du Cigare","Galaxie","Grande Ourse",ephem.readdb("M82,f|G,9:55:52,69:40:47,8.4")),
    ("M101","Galaxie du Moulinet","Galaxie","Grande Ourse",ephem.readdb("M101,f|G,14:03:12,54:20:57,7.9")),
    ("M104","Galaxie du Sombrero","Galaxie","Vierge",ephem.readdb("M104,f|G,12:39:59,-11:37:23,8.0")),
]

PLANETS = [
    ("Mercure", ephem.Mercury()),
    ("Venus",   ephem.Venus()),
    ("Mars",    ephem.Mars()),
    ("Jupiter", ephem.Jupiter()),
    ("Saturne", ephem.Saturn()),
    ("Uranus",  ephem.Uranus()),
    ("Neptune", ephem.Neptune()),
]

def get_tonight_objects():
    obs = get_observer()
    results = []
    for mid, name, typ, const, obj in MESSIER:
        obj.compute(obs)
        alt = float(obj.alt) * 57.2958
        az  = float(obj.az)  * 57.2958
        if alt > 10:
            results.append({
                "id": mid, "name": name, "type": typ,
                "constellation": const,
                "altitude": round(alt, 1),
                "azimuth": round(az, 1),
                "magnitude": str(obj.mag),
                "visible": True,
            })
    results.sort(key=lambda x: -x["altitude"])
    return results

def get_planets():
    obs = get_observer()
    results = []
    for name, planet in PLANETS:
        planet.compute(obs)
        alt = float(planet.alt) * 57.2958
        results.append({
            "name": name,
            "altitude": round(alt, 1),
            "azimuth": round(float(planet.az)*57.2958, 1),
            "magnitude": round(float(planet.mag), 1),
            "visible": alt > 5,
            "phase": round(float(getattr(planet, "phase", 100)), 1),
        })
    return results

def get_stellarium_data():
    obs_objects = get_tonight_objects()
    planets = get_planets()
    visible_planets = [p for p in planets if p["visible"]]
    priority = obs_objects[0] if obs_objects else None
    return {
        "mode": "LIVE_SKY" if obs_objects else "STANDARD",
        "source": "ephem — calcul astronomique réel",
        "location": f"Tlemcen {OBSERVER_LAT}°N {abs(OBSERVER_LON)}°{'W' if OBSERVER_LON < 0 else 'E'}",
        "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fresh": True,
        "objects": obs_objects,
        "count": len(obs_objects),
        "planets": planets,
        "visible_planets": len(visible_planets),
        "priority_object": priority,
    }

def get_priority_object(data=None):
    if data is None:
        data = get_stellarium_data()
    return data.get("priority_object")

if __name__ == "__main__":
    d = get_stellarium_data()
    print(f"Mode: {d['mode']}")
    print(f"Objets Messier visibles: {d['count']}")
    print(f"Planètes visibles: {d['visible_planets']}")
    if d["priority_object"]:
        p = d["priority_object"]
        print(f"Objet prioritaire: {p['name']} à {p['altitude']}° d altitude")
