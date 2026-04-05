#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : DÉTACHEMENT DU WATCHDOG (MODE DAEMON)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

echo "================================================================="
echo "  AEGIS DAEMON : TRANSFERT DU WATCHDOG EN TÂCHE DE FOND"
echo "  Autorisation : Directeur Zakaria Chohra"
echo "================================================================="

# Vérification de l'existence du script maître
if [ ! -f "./astroscan_aegis_watchdog.sh" ]; then
    echo "[!] ERREUR CRITIQUE : Le fichier astroscan_aegis_watchdog.sh est introuvable."
    exit 1
fi

# Lancement silencieux et détaché (nohup)
echo "[*] Injection du processus dans les limbes du serveur..."
nohup ./astroscan_aegis_watchdog.sh > /dev/null 2>&1 &
WATCHDOG_PID=$!

echo "[+] DÉPLOIEMENT RÉUSSI."
echo "-> Le Gardien Aegis surveille désormais AstroScan en arrière-plan."
echo "-> Process ID (PID) attribué : $WATCHDOG_PID"
echo "-> Les données sont toujours enregistrées dans : astroscan_watchdog_log.txt"
echo "-> Vous pouvez fermer votre session SSH en toute sécurité, Chef."