# Phase 4 — Rapport final sécurisation serveur (sans code applicatif)

Date : 2026-04-04

## 1. Fichiers système modifiés

| Fichier | Modification |
|---------|----------------|
| `/etc/nginx/nginx.conf` | `server_tokens off;` activé (masque version nginx). |
| `/etc/nginx/sites-available/astroscan.space` | Ajout `Referrer-Policy` et `Permissions-Policy` (bloc HTTPS). |
| `/etc/systemd/system/astroscan.service.d/limits.conf` | **Créé** : `LimitNOFILE=1048576`. |
| **UFW** | Suppression des règles **allow 5003** (IPv4 + IPv6) — inutiles tant que Gunicorn est sur `127.0.0.1:5003`. |

## 2. Fichiers créés (projet)

| Chemin | Rôle |
|--------|------|
| `ops/SECURITY_PHASE1_AUDIT.md` | Audit lecture seule |
| `ops/SECURITY_PHASE2_PLAN.md` | Plan d’actions safe |
| `ops/backup_astroscan_safe.sh` | Sauvegarde tar.gz (exclusions caches/venv) |
| `ops/README_RESTORE.md` | Procédure de restauration |
| `ops/SECURITY_PHASE4_REPORT.md` | Ce rapport |

## 3. Commandes exécutées (résumé)

- `nginx -t` && `systemctl reload nginx`
- `systemctl daemon-reload` && `systemctl restart astroscan`
- `yes \| ufw delete <rule>` pour retirer 5003 (×2)

## 4. Protections ajoutées

- **UFW** : surface réduite (plus d’ouverture WAN sur 5003).
- **nginx** : pas d’affichage de version (`server_tokens off`), en-têtes navigateur complémentaires sur le vhost HTTPS principal.
- **systemd** : limite descripteurs fichiers relevée pour Gunicorn.
- **Ops** : script de backup + doc restauration + traçabilité audit/plan.

## 5. Recommandations non appliquées (volontairement)

- Durcissement SSH (désactiver mot de passe / root) — risque de lockout sans preuve de clés.
- CSP stricte globale — risque de régression front.
- `limit_req` sur tout le site — risque de 503.
- Sandbox systemd (`ProtectSystem`, `PrivateTmp`, etc.) — risque pour chemins données/logs.
- `chmod` restrictif sur `templates/` — risque si déploiement multi-utilisateur.

## 6. Preuve : code AstroScan non modifié

- **Aucun** changement sous `station_web.py`, `templates/`, `modules/` engines, APIs Flask dans cette mission.
- Vérification suggérée :  
  `test ! -f /root/astro_scan/station_web.py` → faux ;  
  `grep -l SECURITY_PHASE /root/astro_scan/station_web.py` → vide attendu.

## 7. Commandes de vérification finale

```bash
systemctl is-active astroscan
curl -sS -I http://127.0.0.1:5003/health | head -5
curl -sS -I http://127.0.0.1:5003/portail | head -5
curl -sS -I http://127.0.0.1:5003/dashboard-v2 | head -5
ss -tulpn | grep -E ':5003|:80|:443'
ufw status verbose
fail2ban-client status
```

**Attendu** : `astroscan` **active** ; **5003** en **LISTEN** sur **127.0.0.1** uniquement ; HTTP **200** sur les trois URLs ; UFW sans règle **5003** ; fail2ban jails listées.
