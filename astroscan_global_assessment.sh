#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : RADIOGRAPHIE PASSIVE GLOBALE (BILAN DE PRODUCTION)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# DIRECTIVE : LECTURE SEULE STRICTE
# ==============================================================================

set -e

REPORT_FILE="astroscan_production_status_$(date +%Y%m%d_%H%M%S).txt"

echo "=================================================================" > "$REPORT_FILE"
echo "  AEGIS : RADIOGRAPHIE GLOBALE ASTROSCAN (PRODUIT FINI)" >> "$REPORT_FILE"
echo "  Directeur : Zakaria Chohra | Mode : 100% Passif" >> "$REPORT_FILE"
echo "=================================================================" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "[*] Balayage des ressources vitales de la station..."
echo "--- 🖥️ CHARGE SYSTÈME ET MÉMOIRE ---" >> "$REPORT_FILE"
uptime >> "$REPORT_FILE"
free -h | grep -E "Mem|Swap" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "[*] Vérification des fondations de sécurité..."
echo "--- 🛡️ MATRICE DE DÉFENSE (UFW & NGINX) ---" >> "$REPORT_FILE"
ufw status | head -n 4 >> "$REPORT_FILE"
if systemctl is-active --quiet nginx; then
    echo "Bouclier Nginx : ACTIF ET OPÉRATIONNEL" >> "$REPORT_FILE"
else
    echo "Bouclier Nginx : [!] ANOMALIE DÉTECTÉE" >> "$REPORT_FILE"
fi
echo "" >> "$REPORT_FILE"

echo "[*] Contrôle de survie du processus autonome..."
echo "--- ⚙️ GARDIEN AEGIS (DAEMON WATCHDOG) ---" >> "$REPORT_FILE"
DAEMON_PID=$(pgrep -f "astroscan_aegis_watchdog.sh" || echo "INACTIF")
if [ "$DAEMON_PID" != "INACTIF" ]; then
    echo "Processus Watchdog en tâche de fond : ACTIF (PID: $DAEMON_PID)" >> "$REPORT_FILE"
else
    echo "Processus Watchdog : [!] INACTIF OU EFFONDRÉ" >> "$REPORT_FILE"
fi
echo "" >> "$REPORT_FILE"

echo "[*] Inspection de la chambre forte (Sauvegardes)..."
echo "--- 📦 COFFRE-FORT D'ARCHIVAGE ---" >> "$REPORT_FILE"
ls -lh /root/aegis_backups/ | awk '{print $5, $9}' >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "[*] Scan des points de terminaison Web (Locaux)..."
echo "--- 🌐 PORTS DE PRODUCTION ACTIFS ---" >> "$REPORT_FILE"
ss -tln | grep -E "(:80|:443|:5000)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "[+] Radiographie terminée. Génération du bilan pour l'Overlord."
cat "$REPORT_FILE"