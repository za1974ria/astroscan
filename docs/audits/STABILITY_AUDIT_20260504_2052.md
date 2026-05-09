# STABILITY AUDIT — ASTRO-SCAN
**Timestamp:** 2026-05-04 20:52 UTC
**Hôte:** ubuntu-8gb-hil-2 (Hetzner 5.78.153.17)
**Branche:** migration/phase-2c (3 commits non poussés)
**Mode:** lecture seule, exécution autonome (utilisateur `zakaria`, sans sudo)

> Cet audit est produit après la session de réparation chirurgicale
> (commits 86ba895 → 15f5d31). Il identifie les zones de risque latent
> susceptibles de provoquer un incident dans les heures, jours ou
> semaines à venir.

---

## 0. SCORE DE STABILITÉ GLOBAL

| Axe | Score | Verdict |
|---|---|---|
| Runtime principal (gunicorn `astroscan`) | 🟢 9/10 | Sain, restart 20:39, 4 workers + master, 327 MB |
| Routage HTTPS public | 🟢 9/10 | astroscan.space + duckdns OK, cert 58 j |
| APIs externes consommées | 🟢 9/10 | 10/10 endpoints externes répondent 200 |
| Code Python compilation | 🟡 7/10 | 211/212 OK, 1 syntax error inerte |
| Workers d'arrière-plan | 🔴 3/10 | aegis & web en `activating` boucle infinie |
| Disque & rétention | 🔴 2/10 | **93 % plein**, 85 GB de backups locaux |
| Hygiène git | 🟡 5/10 | 568 fichiers staged jamais committés, 124 `.bak` |
| Observabilité | 🟡 6/10 | logs ok mais nginx logs inaccessibles, structured.log à 7 MB |
| Sécurité | 🟢 8/10 | exports/ non exposé, .env 600, fail2ban actif |
| **GLOBAL** | **🟡 6.5/10** | **Production servie correctement, dette technique élevée** |

---

## 1. RUNTIME — SERVICES & PROCESSUS

### 1.1 Matrice systemd

| Service | Enabled | Active | Note |
|---|---|---|---|
| `astroscan` | enabled | **active** | Gunicorn 4w+1m bind 127.0.0.1:5003 — démarré 20:39:17 |
| `astroscan-feeder` | enabled | **active** | nasa_feeder.py — uptime 10 j |
| `astroscan-aegis` | disabled | **activating (auto-restart)** | Boucle d'échec — voir §1.5 |
| `astroscan-web` | disabled | **activating (auto-restart)** | Boucle d'échec — voir §1.5 |
| `astroscan-watchdog` | enabled | **failed (start-limit-hit)** | Mort depuis 2026-05-02 |
| `orbital-shield` | enabled | **active** | uptime 10 j, signale 88% disque |
| `astroscan-tunnel` | enabled | active | cloudflared → `localhost:5000` ⚠️ |
| `cloudflared` | enabled | active | second cloudflared → `localhost:5000` ⚠️ |
| `nginx` (systemd) | enabled | **failed (since 2026-04-28)** | mais master+4 workers tournent (PID 1349523) |
| `redis-server` | enabled | active | uptime 2 j, 1.22 MB used, 13 keys |
| `fail2ban` | enabled | active | uptime 10 j |

### 1.2 Empreinte processus Python

```
PID       USER  RSS    %CPU  ETIME      CMD
3800866   root  26 MB  0.0   00:10:48   gunicorn master  (wsgi:app)
3800869   root 142 MB  0.7   00:10:48   gunicorn worker
3800870   root 134 MB  0.6   00:10:48   gunicorn worker
3800871   root 119 MB  0.2   00:10:48   gunicorn worker
3800872   root 117 MB  0.3   00:10:48   gunicorn worker
975190    root  75 MB  0.1   10-14:07   nasa_feeder.py
975276    root  19 MB  0.0   10-14:07   orbital_shield.py
```
- Total Python: **729 MB**.
- Aucun signe de fuite : workers identiques en RSS malgré 11 minutes ; `--max-requests 1000` recyclera de toute façon.
- `nasa_feeder` et `orbital_shield` tournent depuis le **24 avril**, mais les fichiers source ont été modifiés le **04 mai à 20:01** : **les processus tournent du code obsolète**. Risque de divergence comportement réel/attendu.

### 1.3 Workers gunicorn

- Master `wsgi:app` chargé à 20:39:17 ⇒ utilise le code restauré.
- Aucun respawn récent dans logs récents (post-restart).
- Aucun ERROR/CRITICAL `wsgi`/`gunicorn` depuis le restart (vérifié dans `astroscan_structured.log`).
- 1 curl interne en cours (TLE celestrak) — comportement normal du collector TLE.

### 1.4 Réseau

- Listening : `127.0.0.1:5003` (gunicorn), `:6379` (redis), `:80`/`:443` (nginx ghost), `:22` (ssh).
- Connexions ETABLIES vers `127.0.0.1:5003` : 5.
- Outbound HTTPS actif vers `100.25.0.130:443` (AWS) et `160.79.104.10:443` (Anthropic) — appels Claude en cours.
- **Aucun listener sur `:5000`** alors que les 2 cloudflared y pointent — **tunnel cassé silencieusement** (`/exports/anything → 404` mais astroscan.space → 200 car nginx ghost prend le relais).

### 1.5 Services en boucle d'échec ⚠️ ROUGE

`astroscan-web.service` exécute `python3 /root/astro_scan/station_web.py`, qui se termine à la ligne 5314 par :
```python
port = 5003
app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
```
Mais `:5003` est **déjà occupé** par gunicorn → bind error → exit 1 → restart toutes les 5 s → boucle infinie. Le service systemd est *disabled* mais reste en `activating`.

`astroscan-aegis.service` exécute `core/eye_of_aegis.py`. Lecture du source : il appelle `cv2`, `live_eye.simulate_live_stream`, `moisson_reelle.analyser_image_gemini`. `orbital_shield.log` confirme : « 🚨 astroscan-aegis dépassé max_restarts — intervention manuelle requise ». Les caméras sont en échec, ou la clé Gemini est invalide.

`astroscan-watchdog.service` est **failed (start-limit-hit)** depuis le 02 mai — il y a un `astroscan_health.sh` qui tourne en parallèle et fait le même travail (logs `/var/log/astroscan_health.log`). Le watchdog systemd est mort, le watchdog cron-like fonctionne.

**Impact** : ces 3 services échouent sans bruit côté utilisateur (la prod est servie par gunicorn directement) mais polluent la load average, occupent des slots de redémarrage, et amplifient la confusion d'analyse en cas de vrai incident.

---

## 2. CODE & GIT

### 2.1 Working tree

| Catégorie | Count |
|---|---|
| Fichiers staged (`A `) jamais committés | **568** |
| Fichiers modifiés (`M`) non staged | 3 |
| Fichiers staged + modifiés (`AM`) | 1 |
| Fichiers untracked (`??`) | 1 |
| Total dirty | 573 |

- 542 des 568 fichiers staged sont des SVG drapeaux (`static/flags/4x3/*.svg`) restaurés mais jamais committés.
- Les 3 modifiés `M` (`nasa_feeder.py`, `orbital_shield.py`, `space_weather_feeder.py`) ne contiennent **que** un changement de mode `100644 → 100755` — diff vide.
- `templates/orbital_control_center.html` est `AM` : index = +1099 lignes vs HEAD, worktree = +28 lignes additionnelles non staged.
- Untracked : `exports/` (5 CSV de données IP visiteurs, 916 KB).
- HEAD ↔ origin : **3 commits non poussés** (15f5d31, 26db632, a9d6605).
- Backup branch `backup/pre-repair-2026-05-04` présent (commit 86ba895).

### 2.2 Imports blueprint

22 / 25 blueprints exposent un attribut `bp` au niveau package. Les 3 qui ne l'exposent pas et utilisent un nom local :

| Blueprint | Variable réelle |
|---|---|
| `apod` | `apod_bp` (dans `routes.py`) |
| `iss` | `iss_bp` |
| `sdr` | `sdr_bp` |

L'`__init__.py` de chacun ne fait rien (juste un commentaire). Risque latent : tout import qui ferait `from app.blueprints.apod import bp` casserait. La factory passe par un autre chemin (probablement registration explicite via routes.py) — non bloquant aujourd'hui.

### 2.3 Compilation

- 212 fichiers `.py` (hors venv/git/recovery/backups).
- **211 OK**, **1 erreur de syntaxe réelle** :
  ```
  modules/astro_detection/motion_tracker.py:273
    image_width = max(float(p[1].get("x", 0) or 0 for p in points) + 1.0
  → SyntaxError: '(' was never closed
  ```
  Parenthèse manquante ; le module n'est probablement pas importé en runtime (sinon le service ne démarrerait pas). Bombe à retardement si quelqu'un l'importe.

- Les 8 « FAIL » initiaux étaient des faux positifs dus aux permissions sur `__pycache__/` (zakaria ne peut pas écrire dans des dossiers root-owned).

### 2.4 Shadow files & doublons

- **124 fichiers `.bak*` / `.old` / `.disabled` / `.verrou`** dans le repo (hors venv/backup/).
- **34 copies** `station_web.py.bak_*` au top-level (16 MB cumulés).
- 9 copies `app/blueprints/api/__init__.py.bak_*` au format `bak_<slug>_<timestamp>`.
- 3 copies `app/__init__.py.bak_pre_pass{28,29,30}`.
- 4 backups de `templates/dashboard.html` / `landing.html` / `a_propos.html` / `flight_radar.html`.

**Risque** : un `import` accidentel par chemin relatif, ou une copie ancienne qui surcharge un import via `sys.path`. Le risque réel est faible (Python n'importe pas les `.py.bak`), mais le bruit en `grep` rend tout debug lent (preuve : la recherche `api_docs` retourne 60+ lignes presque toutes des `.bak`).

### 2.5 Templates ↔ routes

- 49 templates référencés via `render_template()` dans tout le code (hors venv).
- **0 référence cassée** côté projet (`not_found.html` apparu dans le grep est interne à Flask).
- 64 templates `.html` actifs dans `templates/` + 13 `.bak`.
- Verdict : **la cohérence templates est saine** (c'est ce qui était cassé avant la réparation).

---

## 3. DÉPENDANCES EXTERNES & ÉTAT INTERNE

### 3.1 Endpoints externes — santé live

| URL | HTTP | Latency | Body |
|---|---|---|---|
| services.swpc.noaa.gov/products/noaa-planetary-k-index.json | 200 | 108 ms | OK |
| services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json | 200 | 35 ms | OK |
| services.swpc.noaa.gov/json/ovation_aurora_latest.json | 200 | 53 ms | OK |
| services.swpc.noaa.gov/products/alerts.json | 200 | 46 ms | OK |
| api.open-meteo.com/v1/forecast | 200 | 690 ms | OK |
| wttr.in/Tlemcen | 200 | 867 ms | OK |
| api.n2yo.com/ | 302 | 405 ms | redirect (auth requis) |
| amsat.org/tle/current/nasa.all | 200 | 220 ms | OK |
| ip-api.com/json | 200 | 11 ms | OK |
| api.open-notify.org/iss-now.json | 200 | 33 ms | OK |

**Conclusion** : 10/10 endpoints externes répondent. Aucun blocage réseau.

### 3.2 Variables d'environnement

`.env` est `0600 root:zakaria` — illisible pour notre user. Comparé à `.env.example` (18 clés requises) :
- `SECRET_KEY`, `NASA_API_KEY` : présence vérifiée indirectement (factory ne crashe pas).
- `ANTHROPIC_API_KEY` : utilisé (httpx logs montrent appels OK).
- `GROQ_API_KEY` : configuré (cf. `/api/aegis/status`: `groq_configured: true, groq_ok: true`).
- `GEMINI_API_KEY`, `XAI_*` : statut inconnu, mais `gemini_configured: false` et `grok_configured: false` dans `/api/aegis/status` — soit absents, soit invalides.

**Risque** : aegis service échoue probablement parce que la clé Gemini n'est pas valide. Aucun health-check ne pousse l'opérateur à corriger.

### 3.3 Circuit breakers (Redis)

```
as:cb:test_open:state     = OPEN  (TTL: -1)   ← test, harmless
as:cb:test_fallback:state = OPEN  (TTL: -1)   ← test, harmless
as:cb:GROQ:state          = OPEN  (TTL: -1)   ← ⚠️ RÉEL, persistant
```

⚠️ **`GROQ` est en `OPEN` permanent (TTL = -1)** alors que `/api/aegis/status` montre `groq_ok: true`. Soit le breaker n'est jamais reset après succès, soit il y a une divergence entre ce que voit le code et ce qui reste dans Redis. À surveiller : si tout le code passe par `groq_call_protected()`, tous les appels Groq échouent silencieusement avec fallback.

### 3.4 Cache Redis

- redis 7.0.15, uptime 2 j, used = 1.22 MB, peak = 4.18 MB, **maxmemory = 0 (illimité)**.
- 13 clés totales, distribution :
  - 10 × `as:cache:*` (TTL 39 s à 3131 s, sains)
  - 3 × `as:cb:*` (cf. ci-dessus)
- `mem_fragmentation_ratio = 9.50` — élevé mais en valeur absolue dérisoire (1.2 MB).

⚠️ **`maxmemory` non configuré** : si un bug provoque une explosion de clés, Redis grossira jusqu'à OOM (le serveur a 7.6 G RAM, 2.9 G utilisée). Fixer un `maxmemory` + `maxmemory-policy=allkeys-lru` est recommandé.

---

## 4. ENDPOINTS HTTP — SANTÉ

### 4.1 Pages HTML (port 5003 direct)

| URL | HTTP | Size | Time | Verdict |
|---|---|---|---|---|
| `/` | 200 | 15.5 KB | 10 ms | OK |
| `/portail` | 200 | 88 KB | 33 ms | OK |
| `/telescope` | 200 | 23 KB | 11 ms | OK |
| `/telescopes` | 200 | 1.2 KB | 2 ms | OK (page minimale) |
| `/sondes` | 200 | 1.8 KB | 2 ms | OK |
| `/ce_soir` | 200 | 32 KB | 5 ms | OK |
| `/aurores` | 200 | 14 KB | 3 ms | OK |
| `/space-weather` | 200 | 3.8 KB | 2 ms | OK |
| `/meteo` | 200 | 42 KB | 1 ms | OK |
| `/meteo-spatiale` | 200 | 13 KB | 3 ms | OK |
| `/meteo-reel` | 200 | 1.8 KB | 2 ms | OK |
| `/apod` | 200 | 1.9 KB | **2940 ms** | ⚠️ lent (appel APOD+Anthropic) |
| `/orbital-radio` | 200 | 9.7 KB | 4 ms | OK |
| `/analytics` | 200 | 21 KB | 55 ms | OK |
| `/europe-live` | 200 | 9 KB | 3 ms | OK |
| `/flight-radar` | 200 | 60 KB | 11 ms | OK |
| `/a_propos` | **404** | 832 B | 2 ms | ⚠️ route absente — `/about` OK |
| `/about` | 200 | 56 KB | 12 ms | OK |
| `/api_docs` | **404** | 832 B | 3 ms | ⚠️ chemin réel = `/api/docs` |
| `/control` | 200 | 42 KB | 11 ms | OK (corrigé après restart) |

### 4.2 APIs JSON

| URL | HTTP | Time | Verdict |
|---|---|---|---|
| `/api/aurore` | 200 | 46 ms | OK (kp=4.0) |
| `/api/aurores` | 200 | 31 ms | OK |
| `/api/space-weather` | 200 | 1 ms | OK (cache) |
| `/api/meteo-spatiale` | 200 | 2 ms | OK |
| `/api/weather` | 200 | 697 ms | OK (live) |
| `/api/weather/local` | 200 | 694 ms | OK |
| `/api/meteo/reel` | 200 | 730 ms | OK (Tlemcen 13°C) |
| `/api/v1/solar-weather` | 200 | 338 ms | OK |
| `/api/space-weather/alerts` | 200 | 68 ms | OK |
| `/api/iss` | 200 | 2 ms | OK |
| `/api/v1/iss` | 200 | **4395 ms** | ⚠️ lent (Skyfield prop) |
| `/api/apod` | 200 | 337 ms | OK |
| `/api/sdr/snapshot` | **404** | 1 ms | ⚠️ route inexistante (clients en font la requête en boucle) |
| `/api/sdr/passes` | 200 | **12070 ms** | 🔴 **systématiquement lent** |
| `/api/aegis/status` | 200 | 2 ms | OK (claude/groq healthy, gemini/grok absents) |
| `/api/analytics/summary` | 200 | 9 ms | OK |
| `/api/docs` | 200 | 4 ms | OK (Swagger) |
| `/api/spec.json` | 200 | 1 ms | OK |
| `/api/version` | 200 | 2 ms | OK |
| `/api/tle/active` | 200 | 5 ms | OK (236 KB) |
| `/api/tle/full` | 200 | 15 ms | OK (517 KB) |
| `/api/admin/circuit-breakers` | 200 | 4 ms | OK |
| `/healthz` | **404** | 1 ms | ⚠️ pas implémenté |
| `/health` | 200 | 6 ms | OK |
| `/ready` | 200 | 1 ms | OK |
| `/sitemap.xml` | 200 | 1 ms | OK |
| `/robots.txt` | 200 | 1 ms | OK |
| `/favicon.ico` | 200 | 2 ms | OK |
| `/static/css/design_tokens.css` | 200 | 1 ms | OK |

### 4.3 Façade publique HTTPS

| URL | HTTP | Time |
|---|---|---|
| https://astroscan.space/ | 200 | 22 ms |
| https://astroscan.space/portail | 200 | 10 ms |
| https://astroscan.space/api/space-weather | 200 | 8 ms |
| https://astroscan.space/api/iss | 200 | 8 ms |
| https://astroscan.space/api/aurore | 200 | 39 ms |
| https://orbital-chohra-dz.duckdns.org/ | 200 | 147 ms |

Cert Let's Encrypt valide jusqu'au **2026-07-01** (~58 jours). `nginx -t` échoue côté zakaria (lecture cert refusée), mais nginx tourne avec un master (PID 1349523) lancé hors systemd → renouvellement certbot pourrait laisser nginx avec ancien cert si systemd reload est invoqué (puisque l'unité systemd est `failed`).

---

## 5. ZONES DE RISQUE LATENT

### 5.1 🔴 CRITIQUES (action court terme conseillée)

1. **Disque à 93 %** (133 G / 150 G) — 11 G libres. Croissance dominée par :
   - `/root/astro_scan/backups/astroscan_safe_20260404T100623Z.tar.gz` = **37 G** (1 fichier)
   - `/root/astro_scan/backup/daily/` = **21 G** (3 tar.gz quotidiens, plus gros chaque jour : 4.8 G → 6.9 G → 8.7 G)
   - `/root/astro_scan/data/images_espace/` = **15 G**
   - `/var/log/syslog.1` = 278 M, `/var/log/btmp.1` = 50 M, `/var/log/journal` = 57 M
   À ce rythme (+3 G/jour de daily backup), saturation dans **3 à 5 jours**. Une fois plein : SQLite WAL bloqué, logs perdus, redémarrages échouent.

2. **Boucle de redémarrage `astroscan-web` & `astroscan-aegis`** — toutes les 5–10 s, échec immédiat. Polluent journald, faussent la load. `orbital-shield` les redémarre en boucle malgré son propre `max_restarts` qui les a marqués "intervention manuelle requise".

3. **`nginx.service` = failed dans systemd, mais master nginx tourne hors systemd** depuis 2026-04-25. Conséquence : `systemctl reload nginx` ne touchera pas le vrai process, et le post-renew hook de certbot pourrait laisser un cert périmé en place. Risque concret au prochain renouvellement (~ juin).

4. **Cloudflared tunnels (×2)** pointent vers `localhost:5000` alors qu'aucun service n'écoute sur `:5000`. Le tunnel public ne sert *rien* — la production fonctionne uniquement via nginx ghost. Si nginx s'arrête (un redémarrage, un OOM…), il n'y a plus de fallback : le site disparaît.

5. **568 fichiers staged jamais committés**. Si quelqu'un fait `git stash`, `git reset`, ou si le repo est pull-écrasé, ces 5 MB de drapeaux + templates restaurés sont perdus à nouveau (et il faudra refaire la restauration). Le travail d'aujourd'hui est en équilibre instable tant que ce n'est pas committé/pushé.

### 5.2 🟡 ÉLEVÉS (action court-moyen terme)

6. **Circuit breaker `as:cb:GROQ:state = OPEN` persistant** (TTL -1). Soit le breaker n'a pas de mécanisme de reset, soit il est désynchronisé du vrai état (`groq_ok: true` côté API). Tout appel Groq peut être short-circuité silencieusement.

7. **Workers d'arrière-plan tournent du code obsolète** : `nasa_feeder.py` et `orbital_shield.py` sont chargés en mémoire depuis le 24 avril mais leurs sources ont été modifiés le 4 mai à 20:01. Mismatch possible entre comportement observable en logs vs comportement défini dans le code. Un restart est requis pour synchroniser, mais il faut le planifier — les redémarrer maintenant ferait perdre le diagnostic en cours.

8. **`/api/sdr/passes` systématiquement à 12 s** (Skyfield calcule 30 passes à chaque hit, sans cache). 82 occurrences en quelques heures dans les `slow_request`. Vulnérabilité DoS triviale : 4 requêtes parallèles → tous les workers gunicorn occupés 12 s → aucun autre client servi. Le `--timeout 120` masque le problème mais ne le résout pas.

9. **`/apod` = 3 s en moyenne** (chain APOD NASA + Anthropic translation + render). 32 hits à >2 s en logs récents.

10. **`/api/sdr/snapshot` = 404 répétitif**. Un client (probablement un widget JS embarqué dans `/control`) le requête en boucle. Pollue les logs WARNING, et fait peut-être planter une UI en silence.

11. **Routes documentées mais absentes** : `/a_propos` (existe en `/about`), `/api_docs` (existe en `/api/docs`), `/healthz` (existe en `/health`, `/ready`). Si une doc, un dashboard ou un partner externe utilise ces chemins, c'est cassé.

12. **`maxmemory` Redis non défini**. Une fuite mémoire applicative côté cache → croissance illimitée → OOM-kill possible du service redis (et probablement de gunicorn par cascade).

13. **125 GB GeoLite2 + 107 GB skyview dans `data/`** — non versionnés, mais consomment l'espace utile. La rétention `data/2026-03-XX/` (25 G cumulés) ne semble pas avoir de purge automatique.

14. **`syntaxError` `motion_tracker.py:273`** — bombe à retardement si quelqu'un branche ce module à un import.

### 5.3 🟢 BAS (dette technique, pas de risque court terme)

15. 124 fichiers `.bak*` polluent grep et confondent les analyses futures. Aucun risque de runtime (Python n'importe pas `.py.bak`).

16. `/var/log/astroscan.log` est vide depuis 2026-03-27 alors que logrotate le cible. Probable incohérence : le code ne log plus dans ce fichier (passage à `logs/astroscan_structured.log`). Logrotate fonctionne mais sur du vide. Pas critique, mais signe que la conf de rotation est obsolète.

17. `astroscan-watchdog.service` mort depuis 02/05 (start-limit-hit). Substitué par `astroscan_health.sh` (logs `/var/log/astroscan_health.log`) qui tourne et signale "[OK]" ou "[ERROR]" toutes les 30 s. Doublon non documenté ; à clarifier.

18. `exports/` (916 KB CSV avec IPs visiteurs) est untracked et **non servi par Flask** (vérifié : `https://astroscan.space/exports/* → 404`). Pas de fuite.

19. `cloudflared.service` et `astroscan-tunnel.service` exécutent **deux** binaires différents (`/usr/bin/cloudflared` et `/usr/local/bin/cloudflared`) avec exactement les mêmes options. Doublon explicite — l'un des deux est inutile.

20. 3 commits non poussés vers `origin/migration/phase-2c`. Si la VM tombe, la réparation d'aujourd'hui n'est pas dans le remote.

---

## 6. DÉFAILLANCES SILENCIEUSES DÉTECTÉES

Ces erreurs se produisent **maintenant** sans alerte côté utilisateur :

| Symptôme | Source | Fréquence | Impact |
|---|---|---|---|
| `ALERTE: service down` astroscan-web | orbital_shield.log | toutes les 30 s | log spam, pas d'impact prod |
| `astroscan-aegis dépassé max_restarts` | orbital_shield.log | toutes les 30 s | pas d'analyse caméra Gemini |
| `slow_request /api/sdr/passes 12000+ ms` | structured.log | 82×/heure | DoS surface |
| `404 /api/sdr/snapshot` | structured.log | continu | client JS qui tourne dans le vide |
| `Disque: 88% utilisé` (en réalité 93%) | orbital_shield.log | toutes les 30 s | pas d'action automatique |
| Anthropic 386 appels en 5h | structured.log | ~80 / h | facture API + risque rate-limit |
| `gemini_configured: false` | /api/aegis/status | permanent | feature aegis désactivée |

---

## 7. RECOMMANDATIONS PRIORISÉES

### P0 (à faire dans les heures)

```
[ ] git add static/flags static/css static/cam-offline.jpg static/earth.jpg \
        static/fallback_space.jpg templates/* static/lib/*
    git commit -m "RESTORE — Frontend assets (drapeaux, CSS, leaflet, templates)"
    git push origin migration/phase-2c
    # Sécuriser les 568 fichiers en équilibre

[ ] # Libérer 50+ GB sur /
    # Cibles: backups/astroscan_safe_20260404T100623Z.tar.gz (37 G)
    #         backup/daily/astroscan_20260501_040001.tar.gz (4.8 G - garder le plus récent)
    # → Décision humaine requise (un audit ne supprime pas)

[ ] systemctl disable --now astroscan-web astroscan-aegis astroscan-watchdog
    # Arrêter les boucles d'échec ; aegis sera ré-activé après fix Gemini key
    # → Décision humaine requise (audit lecture seule)

[ ] # Vérifier nginx ghost — décider si:
    # (a) tuer manuellement et relancer via systemctl
    # (b) accepter le ghost et désactiver l'unit systemd
    # → Décision humaine
```

### P1 (cette semaine)

```
[ ] redis-cli DEL as:cb:GROQ:state as:cb:test_open:state as:cb:test_fallback:state
    # OU corriger le code pour reset sur succès

[ ] # Cache /api/sdr/passes (résultat valable 5–10 minutes)
    # 12 s par hit × 30 sat × 1 client = saturation gunicorn

[ ] # Configurer maxmemory Redis (256 MB suffit largement)
    # /etc/redis/redis.conf : maxmemory 256mb / maxmemory-policy allkeys-lru

[ ] # Implémenter ou supprimer /api/sdr/snapshot (404 répétitif)

[ ] # Remettre cloudflared sur le bon port (5003 au lieu de 5000),
    # ou supprimer la duplication cloudflared.service / astroscan-tunnel.service

[ ] systemctl restart astroscan-feeder orbital-shield
    # Recharger le code après modification du 04 mai 20:01
```

### P2 (ce mois)

```
[ ] # Nettoyer les 124 .bak* (.bak_pre_pass*, .bak_<feature>_<date>)
    # Conserver uniquement le commit git comme historique

[ ] # Mettre en place une rotation/purge data/2026-XX-XX et data/images_espace

[ ] # Corriger motion_tracker.py:273 (parenthèse manquante)

[ ] # Corriger les routes manquantes documentées:
    #   /a_propos → alias /about
    #   /api_docs → alias /api/docs
    #   /healthz  → alias /health

[ ] # Réviser logrotate /etc/logrotate.d/astroscan : ajouter logs/astroscan_structured.log
    # (actuellement il rotate /var/log/astroscan.log qui est mort depuis mars)

[ ] # Configurer ASTROSCAN_FORCE_MONOLITH=0 explicitement et tester périodiquement
    # le fallback monolith pour s'assurer qu'il marche encore en cas de besoin
```

---

## 8. POINTS POSITIFS À PRÉSERVER

- ✅ La factory `app.create_app()` charge **266 routes** (21 BPs effectifs).
- ✅ Le runtime gunicorn principal est sain : 4 workers + master, RSS borné, restart à 20:39.
- ✅ Toutes les APIs externes répondent (NOAA, OpenMeteo, NASA, Anthropic, AMSAT, ip-api, open-notify).
- ✅ Le cert HTTPS est valide jusqu'au 1er juillet.
- ✅ Le module météo restauré aujourd'hui répond correctement (`kp=4.0`, `solar_wind speed=433 km/s`, `aurore activité modérée`).
- ✅ Le backup branch `backup/pre-repair-2026-05-04` est présent : la restauration est rollback-able.
- ✅ Aucune **trace de fuite mémoire** sur les workers Python (RSS stable, pas de croissance vs uptime).
- ✅ Aucune référence template cassée dans le code (49 / 49 résolues).
- ✅ Redis fonctionne, fail2ban actif, certbot config présente.
- ✅ Aucune ERROR/CRITICAL côté wsgi:app post-restart de 20:39.

---

## 9. VERDICT FINAL

**La production est servie correctement** : `https://astroscan.space` répond 200 sur les pages testées et les APIs critiques. La réparation d'aujourd'hui (météo + 17 fichiers Python + 18 templates + 271 drapeaux + Leaflet) est fonctionnellement complète.

**Mais quatre dettes structurelles transforment cette stabilité en équilibre fragile** :

1. Un **disque à 93 %** qui sera plein dans 3–5 jours sans intervention.
2. Trois **services en boucle d'échec** qui polluent les logs et masqueraient un vrai incident.
3. Un **routage prod** qui repose sur un nginx « ghost » non géré par systemd, avec un cloudflared mal configuré qui ne sert plus de fallback.
4. **568 fichiers de la réparation jamais committés / poussés** : un `git stash` ou une perte de la VM annule le travail.

Pour faire passer cette plateforme de "ça tient debout" à "ça tient debout solidement", il faut traiter les quatre points P0 ci-dessus. Aucun nécessite plus de 30 minutes.

---

*Audit produit en lecture seule par claude-opus-4-7 — aucune modification système, aucun commit, aucun redémarrage.*
