#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : AUDIT ET TRAÇAGE DES FLUX API (IDENTIFICATION ANOMALIE HUBBLE)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud 5.78.153.17 (Station Holsboro)
# ==============================================================================

set -e

LOG_FILE="astroscan_api_audit_$(date +%Y%m%d_%H%M%S).txt"
SEARCH_DIR="/root/astro_scan" # Dossier cible selon votre précédente télémétrie

echo "=================================================================" > "$LOG_FILE"
echo "  AEGIS : TRAÇAGE DE L'ANOMALIE DU FLUX 'HUBBLE EN DIRECT'" >> "$LOG_FILE"
echo "  Directeur : Zakaria Chohra" >> "$LOG_FILE"
echo "=================================================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo "[*] Initialisation du scanner sur le répertoire : $SEARCH_DIR"

echo "--- RÉSULTATS DU SCAN (LABEL FRONTEND) ---" >> "$LOG_FILE"
# Recherche du texte exact dans le code frontend
LABEL_MATCH=$(grep -rnwi "$SEARCH_DIR" -e "HUBBLE EN DIRECT" || true)

if [ -n "$LABEL_MATCH" ]; then
    echo "-> Cible identifiée. Le label se trouve dans :" >> "$LOG_FILE"
    echo "$LABEL_MATCH" >> "$LOG_FILE"
else
    echo "-> [!] Label 'HUBBLE EN DIRECT' introuvable dans le répertoire." >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"

echo "--- RECHERCHE DES POINTS DE TERMINAISON API SUSPECTS ---" >> "$LOG_FILE"
# Recherche des appels API génériques de la NASA qui pourraient alimenter cette section
API_MATCH=$(grep -rnoI "$SEARCH_DIR" -e 'https://api.nasa.gov/[a-zA-Z0-9/_-]*' || true)

if [ -n "$API_MATCH" ]; then
    echo "-> API identifiées dans le code source :" >> "$LOG_FILE"
    echo "$API_MATCH" >> "$LOG_FILE"
else
    echo "-> [!] Aucune API NASA en clair détectée dans le code." >> "$LOG_FILE"
fi

echo "[+] Audit de traçage terminé. Rapport généré."
cat "$LOG_FILE"