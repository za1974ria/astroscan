import os
import requests
from datetime import datetime, timezone

BASE_DIR = "/root/astro_scan"
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

def identifier_zone_survol():
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] === ASTRO SCAN : RADAR DE SURVOL TACTIQUE ===")
    print("[STATUT] Triangulation de la position ISS en cours...")
    print("-" * 50)

    try:
        iss_url = "https://api.wheretheiss.at/v1/satellites/25544"
        iss_data = requests.get(iss_url, timeout=10).json()
        lat, lon = iss_data['latitude'], iss_data['longitude']
        print(f"[>] Coordonnées brutes : Latitude {lat:.4f}, Longitude {lon:.4f}")

        geo_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=5"
        headers = {'User-Agent': 'AstroScan-OrbitalChohra/1.0'}
        geo_response = requests.get(geo_url, headers=headers, timeout=10)
        
        if geo_response.status_code == 200:
            geo_data = geo_response.json()
            if 'error' in geo_data:
                print("[i] L'ISS survole actuellement un Océan ou une zone non cartographiée.")
            else:
                zone = geo_data.get('display_name', 'Zone inconnue')
                print(f"[!] CIBLE TERRESTRE IDENTIFIÉE EN DESSOUS :")
                print(f"    -> {zone}")
        else:
            print(f"[X] Radar géographique hors ligne (Code {geo_response.status_code})")

    except Exception as e:
        print(f"[X] ERREUR LIAISON RADAR : {e}")

    print("-" * 50)

if __name__ == "__main__":
    identifier_zone_survol()
