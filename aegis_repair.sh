#!/bin/bash
echo "[AEGIS] 🔴 INITIALISATION DU PROTOCOLE DE RÉPARATION STRICTE..."
sudo systemctl daemon-reload
sudo systemctl stop astroscan
sudo pkill -f gunicorn
sudo pkill -f flask
sleep 2
echo "[AEGIS] 🟢 REDÉMARRAGE DU NOYAU ASTROSCAN..."
sudo systemctl start astroscan
sleep 6
echo "=========================================="
echo "STATUT ACTUEL DU SERVICE :"
sudo systemctl status astroscan --no-pager | grep Active
echo "=========================================="
echo "[AEGIS] RECHERCHE D'ERREURS PYTHON CACHÉES :"
sudo journalctl -u astroscan -n 20 --no-pager | grep -iE "traceback|error|exception|critical|address already in use"
echo "=========================================="
echo "[AEGIS] OPÉRATION TERMINÉE."
