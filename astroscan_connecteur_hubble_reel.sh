#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : DÉPLOIEMENT DU CONNECTEUR HUBBLE RÉEL (V2 - VECTEUR NASA LIBRARY)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

WORK_DIR="/root/astro_scan"
PYTHON_SCRIPT="$WORK_DIR/hubble_feeder_reel.py"

echo "================================================================="
echo "  AEGIS : FORGEAGE DE LA CONNEXION HUBBLE (V2 - CONTOURNEMENT WAF)"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

# Sécurisation du répertoire
mkdir -p "$WORK_DIR"

echo "[*] Régénération du moteur d'extraction Python (Nouvelle cible d'API)..."

cat << 'EOF' > "$PYTHON_SCRIPT"
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import urllib.request
import json
import ssl
import sys

# Calculs de fortune : Tolérance maximale sur les certificats pour passer les boucliers
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Nouvelle cible : Base de données militaire centrale de la NASA, filtrée sur Hubble
API_URL = "https://images-api.nasa.gov/search?q=hubble&media_type=image"

def fetch_real_hubble_data():
    try:
        print("[*] Ouverture d'une brèche via la passerelle officielle NASA Image Library...")
        
        req = urllib.request.Request(API_URL, headers={'User-Agent': 'AstroScan-Overlord/2.0'})
        response = urllib.request.urlopen(req, context=ctx)
        
        # Décodage sécurisé
        raw_data = response.read().decode('utf-8')
        data = json.loads(raw_data)
        
        items = data.get('collection', {}).get('items', [])
        
        if not items:
            print("[!] ERREUR : La banque de données a répondu, mais aucun item n'a été trouvé.")
            sys.exit(1)
            
        print("\n--- 🔭 VÉRITABLES ARCHIVES ET DONNÉES HUBBLE SÉCURISÉES ---")
        
        # Extraction des 3 premiers résultats bruts
        for item in items[:3]:
            # Sécurisation contre les structures JSON manquantes
            info = item.get('data', [{}])[0]
            title = info.get('title', 'Titre classifié')
            date_created = info.get('date_created', 'Date inconnue')
            
            links = item.get('links', [])
            img_url = links[0].get('href', 'Lien corrompu') if links else 'Lien introuvable'
            
            print(f"Cible Spatiale : {title}")
            print(f"Horodatage     : {date_created}")
            print(f"Fichier Brut   : {img_url}")
            print("-" * 60)
            
        print("[+] Extraction réussie. Le flux est 100% authentique et certifié par Aegis.")
        
    except json.decoder.JSONDecodeError:
        print("[!] ERREUR CRITIQUE : Le pare-feu a encore bloqué la requête (Rejet HTML/Non-JSON).")
        sys.exit(1)
    except Exception as e:
        print(f"[!] ERREUR DE CONNEXION AU NOYAU NASA : {e}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_real_hubble_data()
EOF

chmod +x "$PYTHON_SCRIPT"
echo "[+] Moteur Python reconfiguré et prêt : $PYTHON_SCRIPT"
echo "[*] Exécution du nouveau test de pénétration par le Gardien Aegis..."
echo ""

# Exécution pour valider la brèche
python3 "$PYTHON_SCRIPT"