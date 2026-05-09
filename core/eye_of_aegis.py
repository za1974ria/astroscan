from dotenv import load_dotenv
load_dotenv("/root/astro_scan/.env")
"""
REGARD D'AEGIS — Analyse en continu du flux télescope par Gemini 2.5 Flash.
Consomme le flux de live_eye et envoie 1 frame/s à Gemini pour détection d'anomalies.
Failover automatique sur la clé de secours si besoin.
"""
import os
import sys
import time
from pathlib import Path

# Permettre les imports depuis la racine du projet
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import cv2

from core.live_eye import simulate_live_stream
from moisson_reelle import analyser_image_gemini
from core.archive import sauvegarder_observation

TELESCOPE_LIVE = Path(__file__).resolve().parent.parent / "telescope_live"
REPORT_FILE = TELESCOPE_LIVE / "live_report.txt"
CURRENT_LIVE_JPG = TELESCOPE_LIVE / "current_live.jpg"


def verifier_alerte(rapport):
    """Déclenche une alerte (et optionnellement SMS) si mots-clés détectés."""
    mots_cles = ["ufo", "satellite", "anomalie", "ovni", "unknown"]
    if any(mot in rapport.lower() for mot in mots_cles):
        print("!!! ALERTE AEGIS DÉTECTÉE !!!")
        send_script = "/root/sms_project/send_alert.py"
        if os.path.isfile(send_script):
            os.system(f"python3 {send_script} --msg 'Alerte Astro-Scan: Objet détecté par Gemini'")


def surveillance_continue(max_frames=60, fps_analysis=1):
    print("--- [LABORATOIRE] : DÉMARRAGE DU REGARD D'AEGIS ---")
    TELESCOPE_LIVE.mkdir(parents=True, exist_ok=True)

    for frame_data, frame_index, timestamp in simulate_live_stream(
        max_frames=max_frames,
        fps_analysis=fps_analysis,
    ):
        print(f"[{timestamp:.1f}] Frame {frame_index} — Analyse en cours...")
        cv2.imwrite(str(CURRENT_LIVE_JPG), frame_data)

        rapport = analyser_image_gemini(
            frame_data,
            "Analyse cette frame de télescope en direct. Détecte toute anomalie, satellite ou corps céleste.",
        )

        with open(REPORT_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp:.1f}] Frame {frame_index} : {rapport}\n")

        sauvegarder_observation(rapport, image_path=str(CURRENT_LIVE_JPG), source="LIVE_TELESCOPE")
        verifier_alerte(rapport)
        print("--- Rapport archivé pour le Chef ---")
        time.sleep(600)

    print("--- [LABORATOIRE] : FIN DU REGARD D'AEGIS ---")


if __name__ == "__main__":
    surveillance_continue(max_frames=60)
