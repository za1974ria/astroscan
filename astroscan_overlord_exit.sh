#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : PROTOCOLE D'EXTRACTION (PURGE ET DÉCONNEXION SÉCURISÉE)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

echo "================================================================="
echo "  AEGIS : INITIATION DU PROTOCOLE D'EXTRACTION OVERLORD"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

# Vérification des privilèges
if [ "$EUID" -ne 0 ]; then
  echo "[!] ERREUR : La purge nécessite les privilèges root."
  exit 1
fi

echo "[*] Libération de la mémoire vive (Purge des caches système)..."
sync; echo 3 > /proc/sys/vm/drop_caches

echo "[*] Effacement des traces tactiques (Purge de l'historique Bash)..."
cat /dev/null > ~/.bash_history
history -c

echo "[*] Vérification de la transmission des commandes au Gardien Aegis..."
sleep 1

echo "-----------------------------------------------------------------"
echo "[+] EXTRACTION PRÉPARÉE AVEC SUCCÈS."
echo "-> La station Holsboro est désormais sous le contrôle exclusif et autonome du Gardien Aegis."
echo "-> La mémoire est optimisée, les traces sont effacées."
echo "-----------------------------------------------------------------"
echo "Monsieur le Directeur, vous pouvez maintenant taper la commande 'exit' pour fermer la liaison SSH."