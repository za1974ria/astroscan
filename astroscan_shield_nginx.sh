#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : DÉPLOIEMENT DU BOUCLIER NGINX (REVERSE PROXY)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

NGINX_CONF="/etc/nginx/sites-available/astroscan_shield"
NGINX_LINK="/etc/nginx/sites-enabled/astroscan_shield"

echo "================================================================="
echo "  AEGIS : DÉPLOIEMENT DU BOUCLIER INVERSE (NGINX)"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

# Vérification des privilèges
if [ "$EUID" -ne 0 ]; then
  echo "[!] ERREUR : L'Overlord doit exécuter ce script en tant que root."
  exit 1
fi

echo "[*] Installation et activation d'Nginx (si nécessaire)..."
apt-get update -qq && apt-get install -y nginx -qq > /dev/null

echo "[*] Forgeage de la configuration du pare-feu..."
cat << 'EOF' > "$NGINX_CONF"
server {
    listen 80;
    server_name 5.78.153.17 orbital-chohra-dz.duckdns.org;

    # Sécurisation des headers HTTP
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-XSS-Protection "1; mode=block";
    add_header X-Content-Type-Options "nosniff";

    location / {
        # Redirection du trafic web standard vers le moteur principal (Port 5000)
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        # Redirection spécifique pour les API internes (Port 5001/5002)
        proxy_pass http://127.0.0.1:5001;
    }
}
EOF

# Activation du bouclier
echo "[*] Verrouillage de la configuration Nginx..."
ln -sf "$NGINX_CONF" "$NGINX_LINK"
rm -f /etc/nginx/sites-enabled/default

# Rechargement des moteurs
systemctl restart nginx

echo "[+] DÉPLOIEMENT RÉUSSI. Le trafic est désormais filtré et sécurisé par Nginx."
echo "-> Les ports 5000/5001 restent actifs mais sont protégés derrière le bouclier principal."