import os
import json
import subprocess
import requests
import ephem
import math
from datetime import datetime, timezone

# Charger .env si disponible (pour N2YO_API_KEY en contexte cron)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

# CONFIGURATION
BASE_DIR        = os.environ.get("ASTRO_SCAN_ROOT", os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR      = os.path.join(BASE_DIR, "static")
PASS_JSON_PATH  = os.path.join(STATIC_DIR, "passages_iss.json")
ACTIVE_TLE_PATH = os.path.join(BASE_DIR, "data", "tle", "active.tle")

# Tlemcen, Algérie
LAT       = "34.88"
LON       = "1.32"
LAT_F     = 34.88
LON_F     = 1.32
ALT_M     = 800
ISS_NORAD = 25544

CELESTRAK_STATIONS_URLS = (
    "https://celestrak.org/NORAD/elements/stations.txt",
    "http://celestrak.org/NORAD/elements/stations.txt",
)
NETWORK_TIMEOUT_S = 12
N2YO_DAYS         = 7
N2YO_MIN_EL       = 10   # degrés minimum d'élévation

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)


# ── Helpers TLE ──────────────────────────────────────────────────────────────

def _parse_iss_three_lines(lines):
    """Retourne [nom, ligne1, ligne2] pour NORAD 25544."""
    lines = [str(l).strip() for l in lines if str(l).strip()]
    for i in range(len(lines) - 2):
        if lines[i+1].startswith("1 25544") and lines[i+2].startswith("2 25544"):
            return [lines[i], lines[i+1], lines[i+2]]
    return None


def _load_iss_tle_from_local():
    if not os.path.isfile(ACTIVE_TLE_PATH):
        return None, None
    try:
        with open(ACTIVE_TLE_PATH, "r", encoding="utf-8", errors="ignore") as f:
            tle = _parse_iss_three_lines(f.readlines())
        if tle:
            print(f"[TLE] ISS lu depuis fichier local : {ACTIVE_TLE_PATH}")
            return tle, "data/tle/active.tle"
    except Exception as e:
        print(f"[TLE] Lecture locale : {e}")
    return None, None


def _load_iss_tle_from_network():
    for url in CELESTRAK_STATIONS_URLS:
        try:
            resp = requests.get(url, timeout=NETWORK_TIMEOUT_S,
                                headers={"User-Agent": "ORBITAL-CHOHRA/1.0"})
            resp.raise_for_status()
            tle = _parse_iss_three_lines(resp.text.splitlines())
            if tle:
                print(f"[TLE] ISS récupéré en ligne ({url.split('/')[2]})")
                return tle, "celestrak_stations"
        except Exception as e:
            print(f"[TLE] Échec {url[:50]} — {e}")
    return None, None


# ── Source 1 : N2YO API ──────────────────────────────────────────────────────

def _fetch_n2yo_passes():
    """Récupère les passages ISS via N2YO radiopasses (tous passages > N2YO_MIN_EL°)."""
    key = os.environ.get("N2YO_API_KEY", "").strip()
    if not key:
        print("[N2YO] Clé API absente — skip")
        return None

    url = (
        f"https://api.n2yo.com/rest/v1/satellite/radiopasses/"
        f"{ISS_NORAD}/{LAT_F}/{LON_F}/{ALT_M}/{N2YO_DAYS}/{N2YO_MIN_EL}/&apiKey={key}"
    )
    try:
        r = subprocess.run(
            ["curl", "-s", "--ipv4", "--max-time", "15",
             "-A", "ORBITAL-CHOHRA/1.0", url],
            capture_output=True, text=True, timeout=18,
        )
        data = json.loads(r.stdout)
    except Exception as e:
        print(f"[N2YO] Erreur fetch : {e}")
        return None

    passes = data.get("passes", [])
    if not isinstance(passes, list) or not passes:
        print(f"[N2YO] Réponse vide ou invalide")
        return None

    info = data.get("info", {})
    print(f"[N2YO] {len(passes)} passages reçus (sat: {info.get('satname', '?')})")

    results = []
    for p in passes:
        try:
            start_utc = int(p["startUTC"])
            max_utc   = int(p["maxUTC"])
            end_utc   = int(p["endUTC"])

            start_dt = datetime.fromtimestamp(start_utc, tz=timezone.utc)
            max_dt   = datetime.fromtimestamp(max_utc,   tz=timezone.utc)
            end_dt   = datetime.fromtimestamp(end_utc,   tz=timezone.utc)

            dur_min = max(1, round((end_utc - start_utc) / 60))

            results.append({
                "date_utc":              start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "heure_max_utc":         max_dt.strftime("%H:%M:%S"),
                "heure_fin_utc":         end_dt.strftime("%H:%M:%S"),
                "elevation_max_degres":  int(p.get("maxEl", 0)),
                "azimut_depart_degres":  int(round(float(p.get("startAz", 0)))),
                "azimut_fin_degres":     int(round(float(p.get("endAz", 0)))),
                "duree_minutes":         dur_min,
                # Alias frontend
                "date":      start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "heure_max": max_dt.strftime("%H:%M:%S"),
                "elevation": int(p.get("maxEl", 0)),
                "duree":     f"{dur_min} min",
            })
        except (KeyError, TypeError, ValueError) as e:
            print(f"[N2YO] Passage ignoré : {e}")
            continue

    return results if results else None


# ── Source 2 : ephem local (fallback) ───────────────────────────────────────

def _compute_passes_ephem(iss_tle):
    """Calcul orbital local avec ephem — fallback si N2YO indisponible."""
    print("[ephem] Calcul orbital local en cours…")
    iss = ephem.readtle(iss_tle[0], iss_tle[1], iss_tle[2])

    qg = ephem.Observer()
    qg.lat       = LAT
    qg.lon       = LON
    qg.elevation = ALT_M
    qg.date      = ephem.Date(datetime.now(timezone.utc))

    passages = []
    max_iters = 40
    it = 0
    while len(passages) < 5 and it < max_iters:
        it += 1
        tr, azr, tt, altt, ts, azs = qg.next_pass(iss)
        try:
            dur_min = max(1, int(round(float(ts - tr) * 24.0 * 60.0)))
        except Exception:
            dur_min = None

        date_app  = ephem.Date(tr).datetime().strftime("%Y-%m-%d %H:%M:%S")
        heure_max = ephem.Date(tt).datetime().strftime("%H:%M:%S")
        heure_fin = ephem.Date(ts).datetime().strftime("%H:%M:%S")
        az_start  = int(math.degrees(azr))
        elev_max  = int(math.degrees(altt))
        az_end    = int(math.degrees(azs))

        if elev_max > 10:
            dur_str = f"{dur_min} min" if dur_min is not None else "--"
            passages.append({
                "date_utc":              date_app,
                "heure_max_utc":         heure_max,
                "heure_fin_utc":         heure_fin,
                "elevation_max_degres":  elev_max,
                "azimut_depart_degres":  az_start,
                "azimut_fin_degres":     az_end,
                "duree_minutes":         dur_min,
                "date":      date_app,
                "heure_max": heure_max,
                "elevation": elev_max,
                "duree":     dur_str,
            })
        qg.date = ts + ephem.minute * 10

    return passages


# ── Point d'entrée ────────────────────────────────────────────────────────────

def calculer_passages():
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str} UTC] === AstroScan-Chohra — calculateur passages ISS ===")
    print("-" * 55)

    passages   = None
    tle_source = None

    # Tentative 1 : N2YO API (source principale — données précises temps réel)
    print("[>] Source primaire : N2YO radiopasses API…")
    passages = _fetch_n2yo_passes()
    if passages:
        tle_source = f"n2yo_api (radiopasses, élév. min {N2YO_MIN_EL}°)"
        print(f"[✓] N2YO : {len(passages)} passages récupérés")
    else:
        print("[!] N2YO indisponible — bascule sur calcul orbital local (ephem)")

        # Tentative 2 : calcul local ephem (fallback)
        iss_tle, src = _load_iss_tle_from_local()
        if not iss_tle:
            iss_tle, src = _load_iss_tle_from_network()
        if not iss_tle:
            print("[X] ÉCHEC : aucun TLE ISS disponible")
            return

        try:
            passages   = _compute_passes_ephem(iss_tle)
            tle_source = f"ephem_local/{src}"
            print(f"[✓] ephem : {len(passages)} passages calculés")
        except Exception as e:
            print(f"[X] Calcul ephem échoué : {e}")
            return

    if not passages:
        print("[X] Aucun passage calculé — abandon")
        return

    # Sauvegarde atomique
    data = {
        "mise_a_jour_utc":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "coordonnees_radar":  f"Tlemcen, Algérie (Lat {LAT_F}, Lon {LON_F} E)",
        "source_tle":         tle_source,
        "norad_id":           ISS_NORAD,
        "prochains_passages": passages,
    }
    temp_path = PASS_JSON_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(temp_path, PASS_JSON_PATH)

    print(f"[✓] {len(passages)} passages sauvegardés → {PASS_JSON_PATH}")
    print("-" * 55)


if __name__ == "__main__":
    calculer_passages()
