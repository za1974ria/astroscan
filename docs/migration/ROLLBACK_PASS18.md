# ROLLBACK PASS 18 — Bascule wsgi → create_app()

**Date :** 2026-05-03
**Commit bascule :** voir `git log --oneline | grep "PASS 18"`
**Tag de restauration permanent :** `phase-2c-97pct` (commit avant bascule)

---

## ⚠️ Diagnostic rapide après restart astroscan.service

Si quelque chose casse après `systemctl restart astroscan` :

```bash
# 1. Vérifier que gunicorn tourne
systemctl status astroscan

# 2. Lire les logs récents
journalctl -u astroscan -n 100 --no-pager

# 3. Tester les endpoints critiques
curl -fsS https://astroscan.space/api/health
curl -fsS https://astroscan.space/
curl -fsS https://astroscan.space/portail
curl -fsS https://astroscan.space/api/system-status
```

Si HTTP 500 ou logs d'erreur sur `create_app()` :

---

## 🔄 ROLLBACK NIVEAU 1 — Force monolith via env var (le plus rapide)

Aucun code modifié. Active le fallback du `wsgi.py` PASS 18 :

```bash
sudo systemctl edit astroscan
# Ajoute dans la section [Service] :
Environment="ASTROSCAN_FORCE_MONOLITH=1"

sudo systemctl daemon-reload
sudo systemctl restart astroscan
```

Vérifier :
```bash
journalctl -u astroscan -n 30 --no-pager | grep WSGI
# Doit afficher : "[WSGI] Monolith loaded (forced) — N routes"
```

---

## 🔄 ROLLBACK NIVEAU 2 — Revert du commit PASS 18

```bash
cd /root/astro_scan
git log --oneline | head -5
git revert <PASS-18-commit-hash> --no-edit
sudo systemctl restart astroscan
```

`wsgi.py` redevient `from station_web import app` (état avant bascule).

---

## 🔄 ROLLBACK NIVEAU 3 — Reset hard sur tag de restauration

**Destructif** — perd les commits PASS 18+. À utiliser seulement si rollback
1 et 2 échouent :

```bash
cd /root/astro_scan
git fetch --all --tags
git checkout migration/phase-2c
git reset --hard phase-2c-97pct
sudo systemctl restart astroscan
```

---

## ✅ Critères de validation PASS 18 (à vérifier après restart prod)

```bash
# 11 endpoints obligatoires (cf. MIGRATION_PLAN.md §5)
for url in \
  "https://astroscan.space/" \
  "https://astroscan.space/api/iss" \
  "https://astroscan.space/api/health" \
  "https://astroscan.space/portail" \
  "https://astroscan.space/dashboard" \
  "https://astroscan.space/api/apod" \
  "https://astroscan.space/sitemap.xml" \
  "https://astroscan.space/robots.txt" \
  "https://astroscan.space/api/weather" \
  "https://astroscan.space/api/satellites" \
  "https://astroscan.space/api/system-status"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  echo "$code $url"
done
```

Si **un seul** endpoint != 200 → rollback NIVEAU 1 (env var) immédiat.

---

## 📋 Procédure de bascule recommandée pour Zakaria

```bash
# 1. Vérifier l'état avant bascule
cd /root/astro_scan
git log --oneline | head -3
# Doit afficher : "PASS 18 ..."

# 2. Vérifier que le code est valide (aucun crash à l'import)
STATION=/root/astro_scan SECRET_KEY=test python3 -c "
import wsgi
print('OK', len(list(wsgi.app.url_map.iter_rules())), 'routes')
"
# Doit afficher : "OK 262 routes"

# 3. Restart en sudo (le user du service est root)
sudo systemctl restart astroscan
sleep 8

# 4. Vérification immédiate
curl -fsS https://astroscan.space/api/health
journalctl -u astroscan -n 30 --no-pager | grep -E "WSGI|create_app|Monolith"

# 5. Smoke test 11 endpoints (cf. ci-dessus)

# 6. Si tout OK : pousser le tag
cd /root/astro_scan
git tag phase-2c-bascule-ok
git push origin phase-2c-bascule-ok
```

---

## 🧠 Architecture après bascule

```
gunicorn wsgi:app
    └── wsgi.py
        ├── import station_web              # Pré-charge globals (env, DB, threads)
        └── from app import create_app
            └── create_app("production")
                ├── Flask app (template/, static/)
                ├── _init_sentry / _init_sqlite_wal
                └── _register_blueprints  → 21 BPs (260 routes)
                    + Flask default /static/<path:filename>  (= 262 total)
```

Routes restantes dans station_web.py : seulement `/static/<path:filename>`
(override Flask intentionnel — laissé en monolithe car identique au
handler par défaut Flask, pas de gain à migrer).

L'import `import station_web` reste essentiel : les 21 BPs utilisent
`from station_web import _get_db_visitors, _fetch_iss_live, ...` en
lazy-import dans leurs handlers — il faut donc que station_web soit
chargé pour que ces imports trouvent les helpers globaux.
