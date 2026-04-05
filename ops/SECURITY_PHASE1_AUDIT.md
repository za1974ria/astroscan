# Phase 1 — Audit sécurité (lecture seule) — AstroScan

Date : 2026-04-04  
Périmètre : serveur, réseau, services, **aucune modification applicative**.

## 1. Service systemd `astroscan`

- **Unit** : `/etc/systemd/system/astroscan.service`
- **ExecStart** : Gunicorn `127.0.0.1:5003` (binding **loopback uniquement** — bon pour l’isolement réseau).
- **Restart** : `always`, `RestartSec=3`, `StartLimitBurst=10` — résilience correcte.
- **User** : `root` — surface d’attaque élevée en cas de compromission (recommandation future : utilisateur dédié, **hors périmètre** sans refonte).
- **TimeoutStopSec** : 150s — cohérent avec graceful Gunicorn.

## 2. Nginx réellement utilisé

- **Sites activés** : `astroscan`, `astroscan.space`, `orbital-chohra` (symlinks `sites-enabled/`).
- **Production principale** : `astroscan.space` (HTTPS Let’s Encrypt, proxy vers `127.0.0.1:5003`).
- **Headers** : HSTS, `X-Frame-Options`, `X-Content-Type-Options` déjà présents sur `astroscan.space` et `orbital-chohra`.
- **`/etc/nginx/conf.d/aegis_limit.conf`** : zones `limit_req` / `limit_conn` définies mais **non référencées** dans les `server` vus (rate limiting potentiellement inactif).
- **`nginx -t`** : OK.

## 3. Ports ouverts (extraits)

| Port  | Bind        | Service        |
|-------|-------------|----------------|
| 5003  | 127.0.0.1   | Gunicorn AstroScan |
| 80    | 0.0.0.0     | nginx          |
| 443   | 0.0.0.0     | nginx          |
| 22    | 0.0.0.0     | sshd           |

**Constat** : 5003 **n’est pas** exposé sur toutes interfaces — aligné avec le proxy nginx.

## 4. Firewall UFW

- **État** : actif, politique entrante **deny** par défaut.
- **Règles** : 22, 80, 443, **et 5003 ouvert vers l’extérieur**.
- **Risque modéré** : ouvrir 5003 en entrée est **inutile** si l’app n’écoute que sur loopback ; en cas de changement futur de bind vers `0.0.0.0`, cela deviendrait critique.

## 5. SSH (`/etc/ssh/sshd_config`)

- **PermitRootLogin** : `yes` — risque modéré (accès root direct).
- **PasswordAuthentication** : `yes` — risque modéré (bruteforce possible ; fail2ban aide).
- **Recommandation** : clés SSH + désactivation mot de passe **après** validation opérateur — **non appliqué automatiquement** (risque de lockout).

## 6. Fail2ban

- **Présent** : oui.
- **Jails actives** : `sshd`, `nginx-http-auth`, `nginx-botsearch`.

## 7. Permissions (aperçu)

- `/root/astro_scan` : `root:root`, `0755`.
- `templates/` : répertoire en `0775` — groupe/others en lecture/traverse ; pas de world-writable sur fichiers vus.
- **Recommandation** : durcir `templates` en `0750` seulement si aucun autre user ne doit lire — **à décider** (peut casser un déploiement multi-user).

## 8. Stratégie backup actuelle

- Dossier `/root/astro_scan/backup/` avec anciennes copies HTML — pas de procédure datée unique identifiée dans ce scan.
- Scripts existants : `deploy/`, `astroscan_master_aegis_backup.sh`, etc. (non modifiés ici).

## 9. Rotation des logs

- Nginx : `access_log` / `error_log` classiques ; logrotate système présent (non modifié agressivement).

## 10. Exposition publique

- **80 / 443** : nginx (attendu).
- **5003** : **non** exposé sur IP publique (bind 127.0.0.1) ; règle UFW 5003 redondante / risquante en cas d’évolution.

---

## Synthèse risques

### Critiques (contexte actuel)

- Aucun critique bloquant identifié pour la chaîne **Internet → nginx → 127.0.0.1:5003** si la config nginx reste correcte.

### Modérés

- UFW autorisant **5003** en entrée sans nécessité.
- SSH root + mot de passe activés.
- Service AstroScan sous **root**.

### Déjà bien

- Gunicorn en **127.0.0.1:5003**.
- UFW actif, ports standards SSH/HTTP/HTTPS.
- Fail2ban actif (SSH + nginx).
- HTTPS + HSTS sur le vhost principal.
- `Restart=always` sur le service.

### Sécurisable sans toucher au code AstroScan

- Retirer les règles UFW **5003**.
- `server_tokens off` nginx.
- Headers complémentaires (Referrer-Policy, Permissions-Policy) sur vhost HTTPS principal.
- Scripts de backup / doc restauration dans `ops/`.
- Drop-in systemd **LimitNOFILE** uniquement (sans sandbox agressive).
