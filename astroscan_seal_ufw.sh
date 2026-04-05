#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : SCELLAGE DÉFINITIF DU NŒUD (UFW FIREWALL)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

echo "================================================================="
echo "  AEGIS : PROTOCOLE DE SCELLAGE DE LA STATION HOLSBORO"
echo "  Autorisation : Directeur Zakaria Chohra"
echo "  Action : Fermeture blindée des ports non essentiels."
echo "================================================================="

# Vérification des privilèges
if [ "$EUID" -ne 0 ]; then
  echo "[!] ERREUR CRITIQUE : Ce script nécessite les privilèges Overlord (root)."
  exit 1
fi

echo "[*] Réinitialisation des règles de défense de fortune..."
ufw --force reset > /dev/null

echo "[*] Paramétrage de la doctrine de base (Tout refuser en entrée, tout autoriser en sortie)..."
ufw default deny incoming
ufw default allow outgoing

echo "[*] Sécurisation de la liaison Overlord (SSH - Port 22)..."
ufw allow 22/tcp

echo "[*] Autorisation des flux web à travers le bouclier Nginx (Ports 80 & 443)..."
ufw allow 80/tcp
ufw allow 443/tcp

echo "[*] Activation du blindage UFW..."
# Utilisation de --force pour éviter la demande de confirmation qui bloque le script
ufw --force enable

echo "--- 🛡️ VÉRIFICATION DE LA MATRICE DE DÉFENSE ---"
ufw status verbose

echo ""
echo "[+] SCELLAGE RÉUSSI. Le nœud AstroScan est désormais une forteresse."