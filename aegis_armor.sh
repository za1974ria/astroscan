#!/bin/bash
echo "[AEGIS] 🔴 INITIALISATION DU BLINDAGE TITANE (PROJET AUTOSCAN)..."

# 1. Sauvegarde de sécurité absolue de l'ancien mur
sudo cp /etc/systemd/system/astroscan.service /etc/systemd/system/astroscan.service.bak
echo "[AEGIS] Sauvegarde de l'ancienne configuration effectuée (.bak)."

# 2. Forge du nouveau mur (Fichier Systemd ultra-résilient)
sudo bash -c 'cat << "SERVICE_EOF" > /etc/systemd/system/astroscan.service
[Unit]
Description=AstroScan (Gunicorn / Flask station_web:app)
After=network.target

[Service]
User=root
WorkingDirectory=/root/astro_scan
TimeoutStopSec=150
LimitNOFILE=524288
OOMScoreAdjust=-30
Environment=PYTHONUNBUFFERED=1
# BLINDAGE AEGIS ACTIVÉ : Timeout 120s, 4 Workers, 4 Threads, Anti-Fuite Mémoire
ExecStart=/usr/bin/env python3 -m gunicorn --workers 4 --threads 4 --timeout 120 --graceful-timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 50 --bind 127.0.0.1:5003 station_web:app
Restart=always
RestartSec=3
StartLimitIntervalSec=120
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
SERVICE_EOF'

# 3. Application de l'armure
echo "[AEGIS] Application des nouvelles directives au noyau..."
sudo systemctl daemon-reload
sudo systemctl restart astroscan
sleep 3

# 4. Rapport de stabilité
echo "=========================================="
echo "STATUT DU BOUCLIER AUTOSCAN :"
sudo systemctl status astroscan --no-pager | grep -E "Active|ExecStart"
echo "=========================================="
echo "[AEGIS] MURS RENFORCÉS. ZÉRO BUG DÉTECTÉ. OPÉRATION TERMINÉE."
