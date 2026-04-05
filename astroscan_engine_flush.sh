#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : REDÉMARRAGE À FROID DES MOTEURS PYTHON & CORRECTION CACHE
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

TARGET_DIR="/root/astro_scan/templates"

echo "================================================================="
echo "  AEGIS : PURGE THERMIQUE DES MOTEURS PYTHON"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

# 1. Injection sécurisée (Sans le symbole '&' qui peut perturber certains moteurs)
echo "[*] Injection du label définitif : 'NASA APOD ET WEBB'..."
find "$TARGET_DIR" -type f -name "*.html" -exec sed -i 's/HUBBLE EN DIRECT/NASA APOD ET WEBB/g' {} +
find "$TARGET_DIR" -type f -name "*.html" -exec sed -i 's/NASA APOD & WEBB/NASA APOD ET WEBB/g' {} +

# 2. Redémarrage applicatif — UNIQUEMENT systemd / Gunicorn (port 5003, 127.0.0.1).
#    Anciennement : nohup python3 station_web.py → doublon avec Gunicorn + écoute 0.0.0.0:5003.
echo "[*] Arrêt des reliquats station_web.py (mode dev) et restart service astroscan..."
pkill -f "python3.*station_web\.py" 2>/dev/null || true
sleep 2

if systemctl cat astroscan.service &>/dev/null; then
    systemctl restart astroscan || true
    sleep 2
    if systemctl is-active --quiet astroscan 2>/dev/null; then
        echo "-> astroscan : $(systemctl is-active astroscan)"
    else
        echo "-> ERREUR: astroscan inactif — journalctl -u astroscan -n 30" >&2
    fi
else
    echo "-> ATTENTION: unité systemd « astroscan » introuvable. Installez deploy/astroscan.service puis daemon-reload." >&2
fi

echo "-----------------------------------------------------------------"
echo "[+] PURGE ET REDÉMARRAGE TERMINÉS."
echo "-> Les workers Gunicorn relisent les templates ; pas de second serveur Flask en parallèle."
echo "-----------------------------------------------------------------"