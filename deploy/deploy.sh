#!/usr/bin/env bash
# AstroScan — deploy source-unique
# /root/astro_scan  -> /opt/astroscan                    (Flask, gunicorn :5003, user astroscan)
# /root/astro_scan  -> /home/zakaria/astroscan_command_v2 (FastAPI, uvicorn :8000, user zakaria)
#
# REGLE D'OR : /root/astro_scan est la SEULE verite editable. Les deux cibles
# ci-dessus sont des sorties de deploy. NE JAMAIS editer a la main dans /opt
# ou dans astroscan_command_v2. Toujours passer par ce script.
#
# Usage :
#   ./deploy/deploy.sh                          # dry-run (defaut), target=all
#   ./deploy/deploy.sh --target flask           # dry-run sur Flask seul
#   ./deploy/deploy.sh --target command         # dry-run sur Command/FastAPI seul
#   ./deploy/deploy.sh --target all --apply     # applique (necessite root)
#   ./deploy/deploy.sh --apply                  # applique target=all (necessite root)
#
# Le script refuse --apply sans root. Le dry-run tourne en n'importe quel user.
# Le service Flask est relance via deploy/astroscan_reload.sh (existant, garde-fous
# port 5003 + orphelins + health-probe). Le service Command via systemctl direct.

set -euo pipefail
IFS=$'\n\t'

# ─── Config ───────────────────────────────────────────────────────────────────
SRC="/root/astro_scan"

FLASK_DST="/opt/astroscan"
FLASK_OWNER="astroscan:astroscan"
FLASK_UNIT="astroscan"
FLASK_PORT="5003"

CMD_DST="/home/zakaria/astroscan_command_v2"
CMD_SRC_BACKEND="${SRC}/mission_control/backend"
CMD_DST_BACKEND="${CMD_DST}/backend"
CMD_OWNER="zakaria:zakaria"
CMD_UNIT="astroscan-command"
CMD_PORT="8000"

RELOAD_SCRIPT="${SRC}/deploy/astroscan_reload.sh"

# ─── Args ─────────────────────────────────────────────────────────────────────
TARGET="all"
APPLY=0

usage() {
  cat >&2 <<EOF
Usage: $0 [--target flask|command|all] [--apply|--dry-run]

  --target   flask    sync + reload uniquement astroscan.service
             command  sync + reload uniquement astroscan-command.service
             all      les deux (defaut)
  --apply    applique reellement les changements (requiert root)
  --dry-run  affiche ce qui serait fait, ne touche rien (defaut)

Sans --apply, AUCUNE ecriture, AUCUN restart.
EOF
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target)  TARGET="${2:-}"; shift 2 ;;
    --apply)   APPLY=1; shift ;;
    --dry-run) APPLY=0; shift ;;
    -h|--help) usage ;;
    *) echo "Argument inconnu: $1" >&2; usage ;;
  esac
done

case "$TARGET" in
  flask|command|all) ;;
  *) echo "ERREUR: --target doit valoir flask, command ou all" >&2; usage ;;
esac

MODE_LABEL="DRY-RUN"
[ "$APPLY" = "1" ] && MODE_LABEL="APPLY"

# ─── Garde-fous ───────────────────────────────────────────────────────────────
if [ "$APPLY" = "1" ] && [ "$(id -u)" != "0" ]; then
  echo "ERREUR: --apply requiert root (chown + systemctl + ecriture /opt + /home/zakaria/...)." >&2
  exit 2
fi

if [ ! -d "${SRC}/.git" ]; then
  echo "ERREUR: ${SRC} n'est pas un repo git, deploy abandonne." >&2
  exit 2
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "ERREUR: rsync absent." >&2
  exit 2
fi

# Working tree propre obligatoire (sinon on deploierait des changements non commit).
if [ -n "$(git -C "${SRC}" status --porcelain)" ]; then
  echo "ERREUR: working tree sale dans ${SRC}, commit ou stash d'abord." >&2
  git -C "${SRC}" status --short >&2
  exit 2
fi

# ─── Etape A : etat de la source ──────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  AstroScan deploy — mode: ${MODE_LABEL} | target: ${TARGET}"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "── [SOURCE] ${SRC} ──"
git -C "${SRC}" --no-pager log -1 --oneline
LOCAL_HEAD="$(git -C "${SRC}" rev-parse HEAD)"
if git -C "${SRC}" remote get-url origin >/dev/null 2>&1; then
  git -C "${SRC}" fetch --quiet origin 2>/dev/null || \
    echo "  (fetch origin a echoue, on continue sur HEAD local)"
  if ORIGIN_HEAD="$(git -C "${SRC}" rev-parse origin/main 2>/dev/null)"; then
    echo "  Local HEAD : ${LOCAL_HEAD}"
    echo "  origin/main: ${ORIGIN_HEAD}"
    if [ "${LOCAL_HEAD}" != "${ORIGIN_HEAD}" ]; then
      AHEAD="$(git -C "${SRC}" rev-list --count "origin/main..HEAD" 2>/dev/null || echo '?')"
      BEHIND="$(git -C "${SRC}" rev-list --count "HEAD..origin/main" 2>/dev/null || echo '?')"
      echo "  Delta vs origin/main : ahead=${AHEAD}, behind=${BEHIND}"
      echo "  (deploy de l'etat LOCAL, pas de pull automatique)"
    else
      echo "  Sync avec origin/main."
    fi
  fi
fi

# ─── Liste d'exclusion rsync ──────────────────────────────────────────────────
# Doctrine : tout fichier de CODE inclus, tout fichier d'ETAT / RUNTIME / SECRET exclu.
EXCLUDES=(
  # repo git + dev/IDE
  --exclude=".git/"
  --exclude=".github/"
  --exclude=".cursor/"
  --exclude=".claude/"
  --exclude=".pre-commit-config.yaml"
  # caches Python / outillage
  --exclude="__pycache__/"
  --exclude="*.pyc"
  --exclude="*.pyo"
  --exclude=".pytest_cache/"
  --exclude=".ruff_cache/"
  --exclude=".coverage"
  --exclude="coverage.xml"
  # caches user-side du service
  --exclude=".astropy/"
  --exclude=".cache/"
  --exclude=".config/"
  # logs / journaux
  --exclude="*.log"
  --exclude="logs/"
  --exclude="astroscan_watchdog_log.txt"
  # backups manuels et snapshots historiques
  # *.bak* couvre : .bak, .bak_*, .bak-*, .bak.TIMESTAMP, etc.
  --exclude="*.bak*"
  --exclude="*.AVANT_*"
  --exclude="*.pre_restore_*"
  --exclude="*.REPETE_ERREUR"
  --exclude="*.old"
  --exclude="*.verrou"
  --exclude=".snapshots*/"
  --exclude=".archive/"
  --exclude=".deprecated/"
  --exclude="recovery/"
  # venvs (le venv command_v2 est CRITIQUE a preserver)
  --exclude="venv/"
  --exclude=".venv/"
  # etat runtime mutable
  --exclude="data/"
  --exclude="data_core/"
  --exclude="backups/"
  --exclude="backup/"
  --exclude="exports/"
  --exclude="images_espace/"
  # secrets — PRIORITE ABSOLUE
  --exclude=".env"
  --exclude=".env.*"
  # DBs SQLite + ephemerides binaires (mutes runtime / lourds, deja a destination)
  --exclude="*.db"
  --exclude="*.bsp"
  # divers
  --exclude="*.tmp"
  --exclude="*.swp"
)

# ─── Helpers systemd ──────────────────────────────────────────────────────────
service_start_ts() {
  # ActiveEnterTimestamp : moment ou le service est passe "active". Avance a chaque restart.
  systemctl show -p ActiveEnterTimestamp "$1" 2>/dev/null | cut -d= -f2-
}

service_is_active() {
  systemctl is-active --quiet "$1"
}

# ─── Etape B : sync Flask ─────────────────────────────────────────────────────
deploy_flask() {
  echo
  echo "── [FLASK] rsync ${SRC}/ → ${FLASK_DST}/ ──"
  local flags=(-a --delete --human-readable)
  if [ "$APPLY" = "0" ]; then
    flags+=(--dry-run --itemize-changes)
  fi
  rsync "${flags[@]}" "${EXCLUDES[@]}" "${SRC}/" "${FLASK_DST}/"

  if [ "$APPLY" = "1" ]; then
    echo "── chown -R ${FLASK_OWNER} ${FLASK_DST} ──"
    chown -R "${FLASK_OWNER}" "${FLASK_DST}"
  else
    echo "[dry-run] chown -R ${FLASK_OWNER} ${FLASK_DST}"
  fi
}

# ─── Etape B' : sync Command (backend only — frontend non couvert ici) ───────
deploy_command() {
  echo
  echo "── [COMMAND] rsync ${CMD_SRC_BACKEND}/ → ${CMD_DST_BACKEND}/ ──"
  if [ ! -d "${CMD_DST}" ]; then
    echo "ERREUR: ${CMD_DST} n'existe pas." >&2
    exit 2
  fi
  if [ ! -d "${CMD_SRC_BACKEND}" ]; then
    echo "ERREUR: ${CMD_SRC_BACKEND} introuvable dans la source." >&2
    exit 2
  fi
  local flags=(-a --delete --human-readable)
  if [ "$APPLY" = "0" ]; then
    flags+=(--dry-run --itemize-changes)
  fi
  rsync "${flags[@]}" "${EXCLUDES[@]}" "${CMD_SRC_BACKEND}/" "${CMD_DST_BACKEND}/"

  if [ "$APPLY" = "1" ]; then
    echo "── chown -R ${CMD_OWNER} ${CMD_DST_BACKEND} ──"
    chown -R "${CMD_OWNER}" "${CMD_DST_BACKEND}"
  else
    echo "[dry-run] chown -R ${CMD_OWNER} ${CMD_DST_BACKEND}"
  fi
}

# ─── Etape D : reload services ───────────────────────────────────────────────
reload_flask() {
  echo
  echo "── [FLASK] reload via ${RELOAD_SCRIPT} restart ──"
  local before after
  before="$(service_start_ts "${FLASK_UNIT}")"
  echo "ActiveEnterTimestamp avant : ${before:-<inactif>}"
  if [ "$APPLY" = "1" ]; then
    bash "${RELOAD_SCRIPT}" restart
    sleep 2
    after="$(service_start_ts "${FLASK_UNIT}")"
    echo "ActiveEnterTimestamp apres : ${after:-<inactif>}"
    if [ -z "${after}" ] || [ "${before}" = "${after}" ]; then
      echo "ERREUR: ${FLASK_UNIT} n'a pas redemarre (timestamps identiques ou vide)." >&2
      exit 3
    fi
    if ! service_is_active "${FLASK_UNIT}"; then
      echo "ERREUR: ${FLASK_UNIT} pas actif apres restart." >&2
      exit 3
    fi
  else
    echo "[dry-run] bash ${RELOAD_SCRIPT} restart"
  fi
}

reload_command() {
  echo
  echo "── [COMMAND] systemctl restart ${CMD_UNIT}.service ──"
  local before after
  before="$(service_start_ts "${CMD_UNIT}")"
  echo "ActiveEnterTimestamp avant : ${before:-<inactif>}"
  if [ "$APPLY" = "1" ]; then
    systemctl restart "${CMD_UNIT}.service"
    sleep 2
    after="$(service_start_ts "${CMD_UNIT}")"
    echo "ActiveEnterTimestamp apres : ${after:-<inactif>}"
    if [ -z "${after}" ] || [ "${before}" = "${after}" ]; then
      echo "ERREUR: ${CMD_UNIT} n'a pas redemarre." >&2
      exit 3
    fi
    if ! service_is_active "${CMD_UNIT}"; then
      echo "ERREUR: ${CMD_UNIT} pas actif apres restart." >&2
      exit 3
    fi
  else
    echo "[dry-run] systemctl restart ${CMD_UNIT}.service"
  fi
}

# ─── Etape E : verif HTTP ────────────────────────────────────────────────────
verify_flask() {
  echo
  echo "── [VERIF FLASK] curl http://127.0.0.1:${FLASK_PORT}/health ──"
  if [ "$APPLY" = "1" ]; then
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:${FLASK_PORT}/health" || echo 000)"
    echo "/health → HTTP ${code}"
    if [ "${code}" != "200" ]; then
      echo "ERREUR: /health attendu 200, recu ${code}." >&2
      exit 3
    fi
  else
    echo "[dry-run] curl /health"
  fi
}

verify_command() {
  echo
  echo "── [VERIF COMMAND] curl http://127.0.0.1:${CMD_PORT}/healthz ──"
  if [ "$APPLY" = "1" ]; then
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:${CMD_PORT}/healthz" || echo 000)"
    echo "/healthz → HTTP ${code}"
    if [ "${code}" != "200" ]; then
      echo "ERREUR: /healthz attendu 200, recu ${code}." >&2
      exit 3
    fi
  else
    echo "[dry-run] curl /healthz"
  fi
}

# ─── Pipeline ────────────────────────────────────────────────────────────────
case "$TARGET" in
  flask)
    deploy_flask
    reload_flask
    verify_flask
    ;;
  command)
    deploy_command
    reload_command
    verify_command
    ;;
  all)
    deploy_flask
    deploy_command
    reload_flask
    reload_command
    verify_flask
    verify_command
    ;;
esac

echo
echo "════════════════════════════════════════════════════════════════════"
echo "  Fini — ${MODE_LABEL} | target: ${TARGET}"
echo "════════════════════════════════════════════════════════════════════"
