import os
import json
from datetime import datetime, timezone

BASE_DIR = "/root/astro_scan"
STATIC_DIR = os.path.join(BASE_DIR, "static")
VOYAGER_JSON_PATH = os.path.join(STATIC_DIR, "voyager_live.json")

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

def calculer_telemetrie_voyager():
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] === ASTRO SCAN : TRAQUEUR INTERSTELLAIRE ===")
    
    try:
        # Constantes JPL (Epoch 2024-01-01)
        v1_base, v1_vitesse = 24300000000, 16.99
        v2_base, v2_vitesse = 20200000000, 15.30
        
        epoch = datetime(2024, 1, 1, tzinfo=timezone.utc)
        maintenant = datetime.now(timezone.utc)
        secondes_ecoulees = (maintenant - epoch).total_seconds()
        
        v1_dist = v1_base + (secondes_ecoulees * v1_vitesse)
        v2_dist = v2_base + (secondes_ecoulees * v2_vitesse)
        
        v1_latence = (v1_dist / 299792) / 3600
        v2_latence = (v2_dist / 299792) / 3600
        
        data = {
            "mise_a_jour_utc": maintenant.strftime('%Y-%m-%d %H:%M:%S'),
            "voyager_1": {"distance_km": round(v1_dist), "vitesse_km_s": v1_vitesse, "latence_heures": round(v1_latence, 2)},
            "voyager_2": {"distance_km": round(v2_dist), "vitesse_km_s": v2_vitesse, "latence_heures": round(v2_latence, 2)}
        }
        
        temp_path = VOYAGER_JSON_PATH + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_path, VOYAGER_JSON_PATH)
        
        print(f"[✓] CIBLES VERROUILLÉES : VOYAGER 1 & 2")
        print(f"[✓] Fichier généré : {VOYAGER_JSON_PATH}")
        
    except Exception as e:
        print(f"[X] ERREUR : {e}")

if __name__ == "__main__":
    calculer_telemetrie_voyager()
