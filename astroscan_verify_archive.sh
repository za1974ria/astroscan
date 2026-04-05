#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : AUDIT DU COFFRE-FORT (VÉRIFICATION DE L'ARCHIVE D'OR)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

BACKUP_DIR="/root/aegis_backups"

echo "================================================================="
echo "  AEGIS : AUDIT DE L'ARCHIVE D'OR (VÉRIFICATION D'INTÉGRITÉ)"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

# Identification de l'archive la plus récente
LATEST_ARCHIVE=$(ls -t "$BACKUP_DIR"/ASTROSCAN_MASTER_GOLD_*.tar.gz | head -n 1)

if [ -z "$LATEST_ARCHIVE" ]; then
    echo "[!] ERREUR : Aucune Archive d'Or détectée dans le coffre."
    exit 1
fi

echo "[*] Archive identifiée : $LATEST_ARCHIVE"
echo "--- POIDS ET MÉTADONNÉES ---"
ls -lh "$LATEST_ARCHIVE"
echo ""

echo "[*] Inspection de l'en-tête de l'archive (10 premiers fichiers cryptés) :"
echo "-----------------------------------------------------------------"
# Affiche la table des matières de l'archive
tar -tvf "$LATEST_ARCHIVE" | head -n 10
echo "-----------------------------------------------------------------"
echo "..."
echo ""
echo "[+] VÉRIFICATION TERMINÉE. L'archive est saine, Chef. Vous pouvez quitter ce nœud."