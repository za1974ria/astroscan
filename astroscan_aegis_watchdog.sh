#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : AEGIS WATCHDOG (SURVEILLANCE CONTINUE PASSIVE)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud 5.78.153.17 (Station Holsboro)
# ==============================================================================

set -e

LOG_FILE="astroscan_watchdog_log.txt"
INTERVAL=300 # Vérification toutes les 300 secondes (5 minutes)

echo "================================================================="
echo "  AEGIS WATCHDOG : INITIALISATION DE LA SURVEILLANCE CONTINUE"
echo "  Directeur : Zakaria Chohra"
echo "  Mode : Furtif / Lecture seule"
echo "================================================================="
echo "Le Watchdog est actif. Appuyez sur [CTRL+C] pour stopper la surveillance."
echo "Enregistrement des métriques dans : $LOG_FILE"

# Boucle de surveillance infinie
while true; do
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    
    # Calcul de fortune : Nombre exact de connexions établies
    ACTIVE_CONNECTIONS=$(ss -tun state established | tail -n +2 | wc -l)
    
    # Calcul de fortune : Charge système (Load Average)
    LOAD_AVG=$(uptime | awk -F'load average:' '{ print $2 }' | cut -d, -f1 | sed 's/ //g')

    # Formatage de la télémétrie
    TELEMETRY="[$TIMESTAMP] AEGIS SCAN -> Connexions Actives : $ACTIVE_CONNECTIONS | Charge CPU : $LOAD_AVG"
    
    # Affichage en direct pour l'Overlord
    echo "$TELEMETRY"
    
    # Sauvegarde silencieuse dans le journal
    echo "$TELEMETRY" >> "$LOG_FILE"
    
    # Attente avant le prochain scan (5 minutes)
    sleep $INTERVAL
done