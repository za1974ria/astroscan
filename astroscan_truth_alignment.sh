#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : ALIGNEMENT DE LA VÉRITÉ (CORRECTION FRONTEND ET PURGE CACHE)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

TARGET_DIR="/root/astro_scan/templates"

echo "================================================================="
echo "  AEGIS : PROTOCOLE D'ALIGNEMENT DE LA VÉRITÉ"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

echo "[*] Traque et neutralisation du faux label Hubble dans le code frontal..."

# Remplacement brutal dans tous les fichiers HTML du dossier templates
find "$TARGET_DIR" -type f -name "*.html" -exec sed -i 's/HUBBLE EN DIRECT/NASA APOD \& WEBB/g' {} +
find "$TARGET_DIR" -type f -name "*.html*" -exec sed -i 's/HUBBLE EN DIRECT/NASA APOD \& WEBB/g' {} +

echo "[*] Injection réussie. Les titres affichent désormais l'origine exacte des flux."

echo "[*] Purge des caches de la station (Nginx & Système)..."
systemctl restart nginx || echo "[!] Attention : Nginx n'a pas pu redémarrer proprement."
sync; echo 1 > /proc/sys/vm/drop_caches

echo "-----------------------------------------------------------------"
echo "[+] OPÉRATION TERMINÉE."
echo "-> Les mensonges de l'interface ont été purgés."
echo "-----------------------------------------------------------------"