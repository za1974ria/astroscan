#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : AUDIT RÉSEAU GLOBAL ET ÉTAT DES CONNEXIONS (AEGIS)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

LOG_FILE="astroscan_net_audit_$(date +%Y%m%d_%H%M%S).txt"

echo "=================================================================" > "$LOG_FILE"
echo "  AEGIS : RAPPORT D'ÉTAT DES LIEUX DES CONNEXIONS GLOBALES" >> "$LOG_FILE"
echo "  Directeur : Zakaria Chohra | Cible : ASTROSCAN (Holsboro)" >> "$LOG_FILE"
echo "  Horodatage du scan : $(date)" >> "$LOG_FILE"
echo "=================================================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo "[*] Lancement du radar Aegis... Découpage des flux réseau."

echo "--- 🛡️ LIAISONS DE COMMANDEMENT OVERLORD (SSH - PORT 22) ---" >> "$LOG_FILE"
# Affiche uniquement les connexions SSH actives
ss -tun state established '( dport = :22 or sport = :22 )' >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo "--- 🌐 TRAFIC WEB ENTRANT (DASHBOARD - PORTS 80 & 443) ---" >> "$LOG_FILE"
# Affiche les clients connectés au portail web AstroScan
ss -tun state established '( dport = :80 or sport = :80 or dport = :443 or sport = :443 )' >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo "--- 🛰️ FLUX DE DONNÉES SORTANTS (APIs NASA, HUBBLE, ETC.) ---" >> "$LOG_FILE"
# Compte et affiche les adresses IP distantes (hors SSH et Localhost) pour identifier les API
ss -tun state established | grep -v "127.0.0.1" | grep -v ":22" | awk 'NR>1 {print $5}' | cut -d: -f1 | sort | uniq -c | awk '{print $1 " connexion(s) vers IP cible : " $2}' >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo "--- 🔒 SERVICES LOCAUX EN ÉCOUTE (PORTS OUVERTS) ---" >> "$LOG_FILE"
# Cartographie les ports ouverts en attente de connexion
ss -tuln >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo "[+] Balayage terminé. Génération du rapport matriciel."
echo ""

# Affichage immédiat du rapport complet sur le terminal du Directeur
cat "$LOG_FILE"