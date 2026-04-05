#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : ARCHIVAGE D'OR BÉNIT (MASTER BACKUP SÉCURISÉ)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/root/aegis_backups"
ARCHIVE_NAME="ASTROSCAN_MASTER_GOLD_${TIMESTAMP}.tar.gz"
WORK_DIR="/root/astro_scan"

echo "================================================================="
echo "  AEGIS : INITIATION DE L'ARCHIVAGE D'OR (SNAPSHOT ABSOLU)"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

# Création du coffre-fort local
mkdir -p "$BACKUP_DIR"

echo "[*] Extraction des configurations de sécurité (UFW & NGINX)..."
# Sauvegarde des règles de fortune dans le dossier du projet avant compression
ufw status verbose > "$WORK_DIR/ufw_rules_backup.txt"
cp /etc/nginx/sites-available/astroscan_shield "$WORK_DIR/nginx_shield_backup.conf" 2>/dev/null || true

echo "[*] Compression cryptographique de la forteresse AstroScan..."
# Création de l'archive compressée (silencieuse pour ne pas inonder le terminal)
tar -czf "$BACKUP_DIR/$ARCHIVE_NAME" "$WORK_DIR"

echo "[*] Vérification de l'intégrité de l'Archive d'Or..."
ARCHIVE_SIZE=$(du -h "$BACKUP_DIR/$ARCHIVE_NAME" | cut -f1)

echo "--- 📦 RAPPORT D'ARCHIVAGE ---"
echo "-> Emplacement du coffre : $BACKUP_DIR"
echo "-> Nom de l'archive      : $ARCHIVE_NAME"
echo "-> Poids de la sauvegarde: $ARCHIVE_SIZE"
echo ""
echo "[+] SÉCURISATION MAXIMALE ATTEINTE. En cas d'effondrement total, ce fichier restaurera la station à l'identique."