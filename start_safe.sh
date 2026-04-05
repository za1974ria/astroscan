#!/bin/bash
echo "🚀 Démarrage sécurisé AstroScan"
systemctl restart astroscan
systemctl status astroscan --no-pager
