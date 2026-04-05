#!/usr/bin/env bash
# Déploiement nginx + Certbot sur le nœud distant (reverse proxy vers Gunicorn AstroScan).
#
# Prérequis : DNS public du domaine → NODE_IP ; AstroScan sur 127.0.0.1:5003.
# Avant Certbot : créez chez votre registrar / DNS des enregistrements A (et AAAA si besoin)
#   scan.mondomaine.fr  →  <IP publique du serveur>  (souvent la même que NODE_IP)
# Si vous n’avez pas de sous-domaine « www », utilisez :  CERTBOT_INCLUDE_WWW=0
# NXDOMAIN = le nom n’existe pas dans le DNS (pas encore créé ou pas propagé).
# Nginx : un fichier conf.d augmente server_names_hash_* (FQDN longs + www.).
#
# IMPORTANT — Let's Encrypt :
#   Les noms du type *.example.com, example.com, *.test, *.invalid, *.localhost
#   sont réservés (RFC / politique ACME) : aucun certificat ne sera délivré.
#   Utilisez un domaine que vous contrôlez (ex. astroscan.mondomaine.fr).
#   Les libellés du type scan.votre-domaine-reel.tld ou *.tld sont des EXEMPLES :
#   Let's Encrypt répond « invalid public suffix » — enregistrez un vrai domaine chez un registrar.
#
# Usage :
#   export DOMAINE=mon.domaine.fr
#   export CERTBOT_EMAIL=moi@domaine.fr
#   ./deploy/astroscan_nginx_https_deploy.sh
#
#   # ou arguments positionnels (sans export) :
#   ./deploy/astroscan_nginx_https_deploy.sh mon.domaine.fr moi@domaine.fr
#
# Nginx seul (sans Certbot), ex. tests ou domaine réservé :
#   export SKIP_CERTBOT=1
#   export DOMAINE=astroscan.example.com
#   unset CERTBOT_EMAIL   # non requis si SKIP_CERTBOT=1
#   ./deploy/astroscan_nginx_https_deploy.sh
#
# Optionnel : NODE_IP, AEGIS_NODE_IP, ASTROSCAN_PROXY_PORT, AEGIS_SSH_*,
#             CERTBOT_INCLUDE_WWW=0 (ne pas demander www.DOMAINE),
#             SKIP_CERTBOT=1 ou DEPLOY_SKIP_CERTBOT=1
#             DEPLOY_ALLOW_PLACEHOLDER=1  contourne les garde-fous « faux domaine / faux email » (déconseillé)
#             DEPLOY_SKIP_DNS_CHECK=1     ne pas vérifier le DNS avant Certbot (déconseillé)

set -euo pipefail

SKIP_CERTBOT="${SKIP_CERTBOT:-${DEPLOY_SKIP_CERTBOT:-0}}"
CERTBOT_WWW="${CERTBOT_INCLUDE_WWW:-1}"

_truthy_skip() {
  case "${SKIP_CERTBOT}" in 1|true|yes|on|TRUE|YES|ON) return 0 ;; esac
  return 1
}

DOMAINE="${DOMAINE:-${1:-}}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-${2:-}}"

if [[ -z "${DOMAINE}" ]]; then
  echo "[ERREUR] Aucun domaine : définissez DOMAINE ou passez-le en 1er argument." >&2
  echo "" >&2
  echo "  Exemple avec variables :" >&2
  echo "    export DOMAINE=scan.mondomaine.fr" >&2
  echo "    export CERTBOT_EMAIL=moi@mondomaine.fr" >&2
  echo "    $0" >&2
  echo "" >&2
  echo "  Exemple en ligne de commande :" >&2
  echo "    $0 scan.mondomaine.fr moi@mondomaine.fr" >&2
  echo "" >&2
  echo "  HTTP seulement (sans Certbot) :" >&2
  echo "    SKIP_CERTBOT=1 $0 scan.example.com" >&2
  exit 1
fi

NODE_IP="${AEGIS_NODE_IP:-${NODE_IP:-5.78.153.17}}"
REMOTE_USER="${AEGIS_SSH_USER:-root}"
PROXY_PORT="${ASTROSCAN_PROXY_PORT:-5003}"
SSH_TIMEOUT="${AEGIS_SSH_CONNECT_TIMEOUT:-20}"

if ! _truthy_skip; then
  if [[ -z "${CERTBOT_EMAIL}" ]]; then
    echo "[ERREUR] CERTBOT_EMAIL requis pour Let’s Encrypt (ou utilisez SKIP_CERTBOT=1)." >&2
    echo "    export CERTBOT_EMAIL=moi@domaine.fr" >&2
    echo "    ou : $0 ${DOMAINE} moi@domaine.fr" >&2
    exit 1
  fi
else
  CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
fi

if [[ "$DOMAINE" == "votre-domaine.com" ]]; then
  echo "[ERREUR] Remplacez DOMAINE par votre vrai nom de domaine." >&2
  exit 1
fi

# Domaines pour lesquels Let's Encrypt refuse l'émission (politique ACME).
_domain_lc="${DOMAINE,,}"
_le_forbidden=0
case ".${_domain_lc}" in
  *.example.com|*.example) _le_forbidden=1 ;;
esac
case "${_domain_lc}" in
  example.com|example|invalid|localhost) _le_forbidden=1 ;;
esac
case ".${_domain_lc}" in
  *.invalid|*.localhost|*.test) _le_forbidden=1 ;;
esac

if [[ "$_le_forbidden" -eq 1 ]] && ! _truthy_skip; then
  echo "[ERREUR] « ${DOMAINE} » est un nom réservé / interdit par la politique Let's Encrypt." >&2
  echo "         Utilisez un domaine public que vous contrôlez, ou bien :  SKIP_CERTBOT=1  (HTTP seulement)." >&2
  exit 1
fi

# Exemples de tutoriel : pas de TLD public délivrable (ex. finissant par .tld).
_placeholder=0
if [[ "${DEPLOY_ALLOW_PLACEHOLDER:-0}" != "1" ]]; then
  case "${_domain_lc}" in
    *.tld) _placeholder=1 ;;
  esac
  if [[ "${_domain_lc}" == *votre-domaine-reel* || "${_domain_lc}" == *votre-domaine-fictif* ]]; then
    _placeholder=1
  fi
  if [[ "$_placeholder" -eq 1 ]] && ! _truthy_skip; then
    echo "[ERREUR] « ${DOMAINE} » ressemble à un nom d’exemple, pas à un domaine enregistré et résolvable." >&2
    echo "         Achetez ou utilisez un domaine réel (ex. scan.monsite.fr), pointez le DNS vers ce serveur," >&2
    echo "         ou bien :  SKIP_CERTBOT=1  pour n’installer que nginx en HTTP." >&2
    exit 1
  fi
  _em="${CERTBOT_EMAIL,,}"
  if ! _truthy_skip && [[ -n "$_em" ]]; then
    if [[ "$_em" == *votre-mail* || "$_em" == *email-valide* || "$_em" == *@example.com || "$_em" == *@example.org ]]; then
      echo "[ERREUR] CERTBOT_EMAIL semble être un placeholder — indiquez une adresse réelle (compte ACME)." >&2
      echo "         Ou SKIP_CERTBOT=1 pour ignorer Certbot." >&2
      exit 1
    fi
  fi
fi

SSH_BASE=(ssh -q -o "ConnectTimeout=${SSH_TIMEOUT}" -o BatchMode=no)
if [[ -n "${AEGIS_SSH_IDENTITY:-}" ]]; then
  if [[ ! -r "${AEGIS_SSH_IDENTITY}" ]]; then
    echo "[ERREUR] Clé SSH illisible : ${AEGIS_SSH_IDENTITY}" >&2
    exit 1
  fi
  SSH_BASE+=(-i "${AEGIS_SSH_IDENTITY}")
fi

REMOTE="${REMOTE_USER}@${NODE_IP}"

echo "--- [Déploiement : ${DOMAINE} → ${REMOTE} → 127.0.0.1:${PROXY_PORT}] ---"

run_remote() {
  "${SSH_BASE[@]}" "$REMOTE" bash -s -- "$DOMAINE" "$PROXY_PORT" "$CERTBOT_WWW" <<'EOS'
set -eu
D="$1"
P="$2"
W="$3"
if [[ "$W" == "1" ]]; then
  SN="${D} www.${D}"
else
  SN="${D}"
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y nginx certbot python3-certbot-nginx

# FQDN longs (server_name + www.) : le défaut bucket_size=64 fait échouer nginx -t
install -d /etc/nginx/conf.d
cat <<'HASH' >/etc/nginx/conf.d/99-aegis-server-names-hash.conf
# Déployé par astroscan_nginx_https_deploy.sh — ne pas supprimer sans vérifier nginx -t
server_names_hash_bucket_size 256;
server_names_hash_max_size 4096;
HASH

cat <<NGX >/etc/nginx/sites-available/astroscan
server {
    listen 80;
    listen [::]:80;
    server_name ${SN};

    location / {
        proxy_pass http://127.0.0.1:${P};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 15s;
    }
}
NGX

ln -sf /etc/nginx/sites-available/astroscan /etc/nginx/sites-enabled/astroscan
nginx -t
systemctl reload nginx || systemctl restart nginx
echo "[remote] Nginx OK (HTTP → 127.0.0.1:${P})."
EOS
}

run_remote

if _truthy_skip; then
  echo "[OK] Certbot ignoré (SKIP_CERTBOT=1). Service en HTTP : http://${DOMAINE}/"
  echo "    Relancez sans SKIP_CERTBOT une fois un domaine public et le DNS prêts."
  exit 0
fi

# Vérification DNS depuis le nœud (évite une erreur Certbot peu claire type NXDOMAIN).
if [[ "${DEPLOY_SKIP_DNS_CHECK:-0}" != "1" ]]; then
  echo "[DNS] Vérification des enregistrements (résolveur 8.8.8.8)…"
  if ! "${SSH_BASE[@]}" "$REMOTE" bash -s -- "$DOMAINE" "$NODE_IP" "$CERTBOT_WWW" <<'EOS'
set -eu
D="$1"
EXPECT_IP="$2"
WW="$3"
export DEBIAN_FRONTEND=noninteractive
if ! command -v dig >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y dnsutils
fi
check_a() {
  local h="$1"
  local r
  r=$(dig +short A "$h" @8.8.8.8 +time=2 +tries=1 2>/dev/null | head -1 || true)
  if [[ -z "${r}" ]]; then
    echo "[ERREUR] Pas d’enregistrement A pour « $h » (NXDOMAIN ou vide côté DNS public)." >&2
    echo "         Créez :  A  $h  →  $EXPECT_IP  puis attendez la propagation (souvent quelques minutes à 48 h)." >&2
    exit 2
  fi
  if [[ "$r" != "$EXPECT_IP" ]]; then
    echo "[AVERTISSEMENT] « $h » → $r (attendu pour ce script : $EXPECT_IP). Let’s Encrypt peut échouer si ce n’est pas l’IP vue depuis Internet." >&2
  fi
}
check_a "$D"
if [[ "$WW" == "1" ]]; then
  check_a "www.$D"
fi
echo "[DNS] OK (enregistrements A présents)."
EOS
  then
    rc=$?
    if [[ "$rc" -eq 2 ]]; then
      echo "" >&2
      echo "Vérifiez le DNS avec le VRAI nom que vous avez enregistré (pas un libellé d’exemple type « votre-sous-domaine.votredomaine.tld ») :" >&2
      echo "    dig +short A '${DOMAINE}' @8.8.8.8" >&2
      echo "  Une ligne doit afficher l’IP publique du serveur (souvent ${NODE_IP}). Vide = enregistrement A absent ou non propagé." >&2
      if [[ "$CERTBOT_WWW" == "1" ]]; then
        echo "" >&2
        echo "Si vous n’avez pas de « www » dans le DNS :  CERTBOT_INCLUDE_WWW=0  $0 ..." >&2
      fi
      exit 1
    fi
    exit "$rc"
  fi
fi

echo "[Certbot] Obtention du certificat (non interactif)…"
if [[ "$CERTBOT_WWW" == "1" ]]; then
  "${SSH_BASE[@]}" "$REMOTE" bash -s -- "$DOMAINE" "$CERTBOT_EMAIL" <<'EOS'
set -eu
D="$1"
M="$2"
certbot --nginx \
  -d "${D}" -d "www.${D}" \
  --non-interactive --agree-tos \
  -m "${M}" \
  --redirect
EOS
else
  "${SSH_BASE[@]}" "$REMOTE" bash -s -- "$DOMAINE" "$CERTBOT_EMAIL" <<'EOS'
set -eu
D="$1"
M="$2"
certbot --nginx \
  -d "${D}" \
  --non-interactive --agree-tos \
  -m "${M}" \
  --redirect
EOS
fi

echo "[OK] Terminé. Testez : https://${DOMAINE}/"
if [[ "$CERTBOT_WWW" == "1" ]]; then
  echo "    (Si www échoue, vérifiez le DNS pour www.${DOMAINE} ou utilisez CERTBOT_INCLUDE_WWW=0.)"
fi
