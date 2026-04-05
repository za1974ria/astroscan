import os
import json
import requests
from datetime import datetime, timezone

BASE_DIR = "/root/astro_scan"
STATIC_DIR = os.path.join(BASE_DIR, "static")
WEATHER_JSON_PATH = os.path.join(STATIC_DIR, "space_weather.json")

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

def synchroniser_meteo_spatiale():
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] === ASTRO SCAN : MÉTÉOROLOGIE SPATIALE (NOAA) ===")
    print("[STATUT] Interception des vents solaires et radiations cosmiques...")
    print("-" * 50)

    try:
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        headers = {'User-Agent': 'OrbitalChohra-Aegis/1.0'}
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            derniere_mesure = data[-1]
            kp_index = float(derniere_mesure[1])

            statut = "NOMINAL (VERT)"
            alerte = "Activité solaire calme. Radiations normales."
            
            if kp_index >= 5.0:
                statut = "ALERTE G1-G5 (TEMPÊTE GÉOMAGNÉTIQUE - ROUGE)"
                alerte = "Risque critique de radiations (Pixels chauds ISS extrêmes) et coupures radio (LOS) imminentes."
            elif kp_index >= 4.0:
                statut = "AVERTISSEMENT (INSTABILITÉ MAGNÉTIQUE - ORANGE)"
                alerte = "Augmentation des vents solaires. Aurores boréales massives aux pôles."

            weather_data = {
                "mise_a_jour_utc": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                "kp_index": kp_index,
                "statut_magnetosphere": statut,
                "impact_orbital": alerte,
                "source": "NOAA Space Weather Prediction Center"
            }

            temp_path = WEATHER_JSON_PATH + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(weather_data, f, indent=4, ensure_ascii=False)
            os.replace(temp_path, WEATHER_JSON_PATH)

            print(f"[✓] INDICE Kp ACTUEL : {kp_index}")
            print(f"[>] ÉTAT DU BOUCLIER TERRESTRE : {statut}")
            print(f"[✓] Télémétrie météo synchronisée : {WEATHER_JSON_PATH}")
        else:
            print(f"[X] ÉCHEC LIAISON NOAA. Code: {response.status_code}")

    except Exception as e:
        print(f"[X] ERREUR DU SOUS-SYSTÈME MÉTÉO SPATIALE : {e}")

    print("-" * 50)

if __name__ == "__main__":
    synchroniser_meteo_spatiale()
