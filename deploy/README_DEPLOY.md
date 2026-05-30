# Deploy AstroScan — source unique

## Règle d'or

**`/root/astro_scan` est la SEULE vérité éditable.**

- `/opt/astroscan` (Flask, gunicorn :5003, user `astroscan`) — **cible de deploy**, jamais à éditer à la main.
- `/home/zakaria/astroscan_command_v2` (FastAPI, uvicorn :8000, user `zakaria`) — **cible de deploy**, jamais à éditer à la main.

Toute modif de code part de `/root/astro_scan`, est commitée git, puis propagée via `deploy/deploy.sh`. Pas d'édition directe dans les cibles, sinon les éditions seront écrasées au prochain deploy ou créeront une divergence silencieuse (le bug qu'on a tué cette nuit).

## Topologie

| Service                       | Cible runtime                        | User      | Port  | Venv                                               |
| ----------------------------- | ------------------------------------ | --------- | ----- | -------------------------------------------------- |
| `astroscan.service`           | `/opt/astroscan/`                    | astroscan | 5003  | aucun (system python3, packages globaux)           |
| `astroscan-command.service`   | `/home/zakaria/astroscan_command_v2/`| zakaria   | 8000  | `/home/zakaria/astroscan_command_v2/.venv/`        |

Le Makefile cible `restart` ne relance QUE `astroscan` — `deploy/deploy.sh` couvre **les deux**.

## Usage

```bash
# Dry-run (defaut, AUCUNE ecriture, n'importe quel user) :
./deploy/deploy.sh                          # target=all, dry-run
./deploy/deploy.sh --target flask           # Flask seul, dry-run
./deploy/deploy.sh --target command         # Command seul, dry-run

# Apply (requiert root) :
sudo ./deploy/deploy.sh --apply             # target=all
sudo ./deploy/deploy.sh --target flask --apply
sudo ./deploy/deploy.sh --target command --apply
```

Le script :

1. Vérifie que le working tree git est **propre** (sinon stop, message actionnable).
2. Affiche `HEAD` local vs `origin/main` (delta ahead/behind). **Aucun pull automatique** — on déploie l'état LOCAL commité.
3. Rsync `--delete` avec la liste d'exclusion (cf. ci-dessous), source → cible.
4. `chown -R` sur l'owner cible (`astroscan:astroscan` pour /opt, `zakaria:zakaria` pour command_v2).
5. Reload : `deploy/astroscan_reload.sh restart` pour Flask (réutilise garde-fous port 5003 + orphelins + probe `/api/aegis/status`), `systemctl restart astroscan-command.service` pour Command.
6. Vérifie post-restart : `ActiveEnterTimestamp` doit avoir avancé + `is-active`. Sinon erreur explicite.
7. `curl /health` (5003) et `/healthz` (8000) doivent renvoyer 200.

## Liste d'exclusion rsync

Tout fichier de **code** est synchronisé. Tout fichier d'**état / runtime / secret** est exclu.

| Catégorie        | Patterns                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| Git/IDE/dev      | `.git/` `.github/` `.cursor/` `.claude/` `.pre-commit-config.yaml`     |
| Caches Python    | `__pycache__/` `*.pyc` `*.pyo` `.pytest_cache/` `.ruff_cache/` `.coverage` `coverage.xml` |
| Caches service   | `.astropy/` `.cache/` `.config/`                                        |
| Logs             | `*.log` `logs/` `astroscan_watchdog_log.txt`                            |
| Backups manuels  | `*.bak` `*.bak_*` `*.AVANT_*` `*.pre_restore_*` `*.REPETE_ERREUR`        |
| Snapshots        | `.snapshots*/` `.archive/` `.deprecated/` `recovery/`                   |
| Venvs            | `venv/` `.venv/` (le venv command_v2 est **critique** à préserver)      |
| État runtime     | `data/` `data_core/` `backups/` `backup/` `exports/` `images_espace/`   |
| **Secrets**      | `.env` `.env.*` — les fichiers `.env` divergent entre /root et /opt, ne jamais écraser |
| DBs + éphémérides| `*.db` `*.bsp` (mutés runtime / lourds, présents à destination)         |
| Divers           | `*.tmp` `*.swp`                                                         |

`rsync --delete` ne supprime que ce qui est synchronisé : les chemins exclus restent intacts côté cible (et notamment `.env`, `data/`, `.venv/`, etc.).

## Pré-requis avant `--apply` réel

- Working tree git propre (`git status` clean).
- `astroscan.service` et `astroscan-command.service` actifs avant deploy (sinon le check d'`ActiveEnterTimestamp` n'a pas de baseline).
- Si `requirements.txt` a changé pour le Flask : `pip install` manuel côté system python AVANT de lancer `--apply` (le script ne touche pas aux deps).
- Si le venv `astroscan_command_v2/.venv` a besoin d'un `pip install` : le faire manuellement avant `--apply` (le script ne touche pas au venv).

## Rollback

Tag git posé avant chaque session de modif (cf. `git tag --list "pre-*"`). En cas de pépin après `--apply` :

```bash
# Revert le commit fautif dans /root
cd /root/astro_scan
git revert <bad-sha>
git push
# Re-deploy
sudo ./deploy/deploy.sh --apply
```

Ou bascule rapide via le script existant :

```bash
bash /root/astro_scan/deploy/astroscan_reload.sh restart   # juste relance Flask
systemctl restart astroscan-command.service                 # juste relance Command
```
