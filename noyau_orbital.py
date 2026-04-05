import os
import sys
import requests
import json
import re
from datetime import datetime, timedelta

# CONFIGURATION DU CHEMIN SÉCURISÉ
BASE_DIR = "/root/astro_scan"
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

def demarrer_noyau_orbital():
    print(f"[{datetime.now()}] === ORBITAL-CHOHRA : NOYAU V2.0 ===")
    print("[STATUT] Scan des fréquences : Orbite Basse, Mars, et Espace Profond...")
    print("-" * 50)

    # 1. TÉLÉMÉTRIE ISS (Temps Réel)
    try:
        iss_req = requests.get("http://api.open-notify.org/iss-now.json", timeout=10)
        iss_data = iss_req.json()
        iss_pos = iss_data['iss_position']
        print(f"[✓] CIBLE VERROUILLÉE : ISS (Orbite Terrestre Basse)")
        print(f"    - Latitude  : {iss_pos['latitude']}")
        print(f"    - Longitude : {iss_pos['longitude']}")
    except Exception as e:
        print(f"[X] ERREUR LIAISON ISS : {e}")

    print("-" * 50)

    # 2. PHOTOS MARS (Rover Curiosity)
    try:
        mars_url = "https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos?api_key=DEMO_KEY"
        mars_req = requests.get(mars_url, timeout=10)
        mars_data = mars_req.json()
        
        if 'latest_photos' in mars_data and len(mars_data['latest_photos']) > 0:
            derniere_photo = mars_data['latest_photos'][0]
            print(f"[✓] CIBLE VERROUILLÉE : MARS (Rover {derniere_photo['rover']['name']})")
            print(f"    - Date Terrestre : {derniere_photo['earth_date']}")
            print(f"    - Caméra         : {derniere_photo['camera']['full_name']}")
        else:
            print("[i] CIBLE MARS : Aucune nouvelle transmission d'image aujourd'hui (Attente DSN).")
    except Exception as e:
        print(f"[X] ERREUR LIAISON MARS : {e}")

    print("-" * 50)

    # 3. TÉLÉMÉTRIE VOYAGER 1 (Espace Interstellaire via NASA JPL Horizons)
    try:
        aujourdhui = datetime.utcnow().strftime('%Y-%m-%d')
        jpl_url = "https://ssd.jpl.nasa.gov/api/horizons.api"
        params = {
            "format": "json",
            "COMMAND": "'-31'",
            "OBJ_DATA": "'NO'",
            "MAKE_EPHEM": "'YES'",
            "EPHEM_TYPE": "'VECTORS'",
            "CENTER": "'@399'",
            "START_TIME": f"'{aujourdhui}'",
            "STOP_TIME": f"'{aujourdhui} 00:01'",
            "STEP_SIZE": "'1d'"
        }
        
        v1_req = requests.get(jpl_url, params=params, timeout=15)
        v1_data = v1_req.json()
        
        if "result" in v1_data:
            match = re.search(r'RG= *([0-9\.E\+\-]+)', v1_data["result"])
            if match:
                dist_km = float(match.group(1))
                dist_au = dist_km / 149597870.7
                vitesse_lumiere_km_s = 299792.458
                delai_signal_heures = (dist_km / vitesse_lumiere_km_s) / 3600
                
                print(f"[✓] CIBLE VERROUILLÉE : VOYAGER 1 (Espace Interstellaire)")
                print(f"    - Distance Terre : {dist_km:,.0f} km ({dist_au:.2f} AU)")
                print(f"    - Délai Radio    : {delai_signal_heures:.2f} heures (Aller simple)")
            else:
                print("[!] Données Voyager 1 reçues mais format illisible.")
        else:
            print("[!] API Horizons injoignable pour Voyager 1.")

    except Exception as e:
        print(f"[X] ERREUR LIAISON VOYAGER 1 : {e}")

    print("-" * 50)
    print("[ASTRO SCAN] Séquence de balayage terminée.")

if __name__ == "__main__":
    demarrer_noyau_orbital()
