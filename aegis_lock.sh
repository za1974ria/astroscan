#!/usr/bin/env bash
# Verrouillage précision — bannir une IP entrante sur le nœud (iptables).
#
# Important : ne pas utiliser « ssh … bash -s <<EOF » : le heredoc occupe stdin et
# empêche la saisie du mot de passe. Les commandes distantes sont passées en argument.
#
# Usage :
#   ./aegis_lock.sh
#   AEGIS_LOCK_IP=203.0.113.50 AEGIS_NODE_IP=5.78.153.17 ./aegis_lock.sh
#   AEGIS_SSH_IDENTITY=/root/.ssh/id_ed25519 ./aegis_lock.sh
#   AEGIS_SSH_BATCH=1 ./aegis_lock.sh    # idem WATCHER_SSH_BATCH=1 — cron / clé uniquement
#
# Variables : AEGIS_SSH_USER (défaut root), AEGIS_SSH_IDENTITY
#             AEGIS_SSH_BATCH ou WATCHER_SSH_BATCH=1 → BatchMode=yes (cron / clé)
#             AEGIS_NODE_IP / HILLSBORO_NODE_IP → IP du nœud (défaut 5.78.153.17)
#             AEGIS_LOCK_IP → IP à bannir (défaut ci-dessous)

set -euo pipefail

TARGET_IP="${AEGIS_LOCK_IP:-105.235.137.132}"
NODE_IP="${AEGIS_NODE_IP:-${HILLSBORO_NODE_IP:-5.78.153.17}}"
REMOTE_USER="${AEGIS_SSH_USER:-root}"
SSH_TIMEOUT="${AEGIS_SSH_CONNECT_TIMEOUT:-20}"

SSH_CMD=(ssh -q -o "ConnectTimeout=${SSH_TIMEOUT}")
if [[ "${AEGIS_SSH_BATCH:-0}" == "1" || "${WATCHER_SSH_BATCH:-0}" == "1" ]]; then
  SSH_CMD+=(-o BatchMode=yes)
else
  SSH_CMD+=(-o BatchMode=no)
fi
if [[ -n "${AEGIS_SSH_IDENTITY:-}" ]]; then
  if [[ ! -r "$AEGIS_SSH_IDENTITY" ]]; then
    echo "[ERREUR] Clé privée introuvable ou non lisible : $AEGIS_SSH_IDENTITY" >&2
    echo "        Exemples : ls -la /root/.ssh/id_ed25519 /root/.ssh/id_rsa" >&2
    exit 1
  fi
  SSH_CMD+=(-i "$AEGIS_SSH_IDENTITY")
fi

# Commande distante sur une ligne : stdin reste le terminal → saisie du mot de passe possible.
# (Un heredoc vers « ssh … bash -s » monopolise stdin et casse l’auth par mot de passe.)
REMOTE_SH="set -eu; iptables -C INPUT -s ${TARGET_IP} -j DROP 2>/dev/null || iptables -A INPUT -s ${TARGET_IP} -j DROP; mkdir -p /etc/iptables; iptables-save > /etc/iptables/rules.v4; echo '[remote] Règle appliquée et sauvegardée.'"

echo "[AEGIS] Verrouillage de l'IP : $TARGET_IP sur le nœud $NODE_IP (${REMOTE_USER})..."
if ! "${SSH_CMD[@]}" "${REMOTE_USER}@${NODE_IP}" "$REMOTE_SH"; then
  echo "" >&2
  echo "[ERREUR] SSH a échoué vers ${REMOTE_USER}@${NODE_IP}." >&2
  echo "" >&2
  echo "Pistes :" >&2
  echo "  - Mot de passe : par défaut BatchMode=no (ne pas mettre AEGIS_SSH_BATCH=1)." >&2
  echo "  - Clé : ssh-copy-id … ou AEGIS_SSH_IDENTITY=/chemin/clé_privée $0" >&2
  echo "  - Cron sans TTY : AEGIS_SSH_BATCH=1 et authentification par clé uniquement." >&2
  exit 1
fi

echo "[OK] IP bannie et configuration sauvegardée sur le serveur distant."
