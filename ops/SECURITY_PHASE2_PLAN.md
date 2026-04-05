# Phase 2 — Plan d’exécution SAFE (classé du plus sûr au plus sensible)

| Ordre | Action | Changement | Impact AstroScan | Rollback | Redémarrage |
|-------|--------|------------|------------------|----------|-------------|
| 1 | Documentation `ops/` (audit + backup + restore) | Fichiers nouveaux sous `/root/astro_scan/ops/` | Aucun | Supprimer les fichiers | Non |
| 2 | Script `ops/backup_astroscan_safe.sh` | Archive datée hors répertoire métier critique | Aucun (lecture seule + tar) | Supprimer script | Non |
| 3 | UFW : retirer allow **5003** (IPv4 + IPv6) | Pare-feu : plus d’entrée WAN sur 5003 | Aucun : l’app écoute 127.0.0.1 ; nginx/localhost inchangés | `ufw allow 5003/tcp` | Non |
| 4 | nginx : `server_tokens off` dans `nginx.conf` | Masque version nginx dans headers | Aucun | Remettre en commentaire | `nginx -s reload` |
| 5 | nginx : en-têtes Referrer-Policy + Permissions-Policy sur `astroscan.space` (HTTPS) | Headers HTTP supplémentaires | Aucun sur routes Flask | Retirer les lignes | `nginx -s reload` |
| 6 | systemd drop-in `LimitNOFILE` | Plafond descripteurs fichiers | Aucun sur logique Python | Supprimer drop-in + `daemon-reload` | `systemctl daemon-reload` puis `restart astroscan` |

## Non exécuté automatiquement (recommandations)

- **SSH** : désactiver mot de passe / restreindre root — risque de perte d’accès.
- **CSP** stricte nginx — risque de casser inline scripts / PWA.
- **Rate limiting** global sur `/` — risque de 503 pour utilisateurs légitimes.
- **ProtectSystem=** / **PrivateTmp=** sur le service — risque de casser écritures chemins.
- **Chmod templates** — risque opérationnel si autre user lit les fichiers.
