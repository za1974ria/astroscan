# AstroScan — déploiement synchro vue (`/ws/view-sync`)

## Variables d’environnement

| Variable | Obligatoire | Description |
|----------|-------------|-------------|
| `REDIS_URL` | Non | URL Redis pour multi-workers + persistance du dernier `VIEW_STATE` + verrou **MASTER** partagé. Ex. `redis://localhost:6379/0` |
| `VIEW_SYNC_LAST_TTL` | Non | TTL secondes de la clé dernier état (défaut `604800` = 7 jours) |
| `VIEW_SYNC_MASTER_TTL` | Non | TTL secondes du verrou master en Redis (défaut `86400` = 24 h) |
| `VIEW_SYNC_MASTER_STALE` | Non | Secondes sans heartbeat / activité master avant libération du verrou (défaut `15`) |
| `VIEW_SYNC_HEARTBEAT_TTL` | Non | TTL Redis de la clé heartbeat (défaut `18`, doit rester > `VIEW_SYNC_MASTER_STALE`) |
| `VIEW_SYNC_SESSION_KEY` | Non | Si défini, le WebSocket **doit** inclure `?sessionKey=` identique (octets UTF-8 comparés avec `secrets.compare_digest`) |

## Exemple `REDIS_URL`

```bash
export REDIS_URL="redis://:motdepasse@127.0.0.1:6379/0"
```

Docker Compose (extrait) :

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  astroscan:
    environment:
      REDIS_URL: redis://redis:6379/0
```

## Mode dev (sans Redis)

- Aucune variable : hub **local** (un seul processus).
- Dernier état + verrou master sont **en mémoire processus** (perdus au redémarrage).
- **Gunicorn multi-workers** sans Redis : chaque worker a sa propre mémoire → synchro incomplète entre clients sur workers différents.

## Mode prod (recommandé)

1. Lancer Redis accessible depuis tous les workers.
2. Définir `REDIS_URL`.
3. Logs attendus au démarrage du premier hub :
   - `VIEW_SYNC: Redis OK — ...`
   - `VIEW_SYNC: OK MULTI-WORKER — Redis actif (diffusion inter-workers).`
4. Worker WebSocket compatible (gevent, etc.) selon la stack Flask.

## Query WebSocket

Connexion : `/ws/view-sync?sessionId=...&viewRole=...&sourceDevice=...&sessionKey=...`

- **sourceDevice** : identifiant stable (JS) — base du verrou master.
- **sessionKey** : obligatoire si `VIEW_SYNC_SESSION_KEY` est défini sur le serveur.
- **Heartbeat** : le client **master** envoie un message JSON `{"type":"HEARTBEAT",...}` toutes les ~5 s ; chaque `VIEW_STATE` master rafraîchit aussi le heartbeat. Sans activité > `VIEW_SYNC_MASTER_STALE`, le serveur libère le verrou (`VIEW_SYNC: MASTER TIMEOUT`).
- **Takeover** : message `{"type":"REQUEST_MASTER",...}` ; refus `ROLE_UPDATE` + `reason: master_active` si le master est vivant ; sinon prise du verrou + `ROLE_UPDATE` + `role: master`.
- **Init** : `VIEW_STATE` avec `messageKind: "init"` est toujours appliqué côté client (pas de filtre `sourceDevice`).

## Frontend — URL pages carte

- `?sessionId=demo-1`
- `?viewRole=master` | `viewer` | `collaborative`

Exemple :

- PC : `/orbital-map?sessionId=demo-1&viewRole=master`
- Android : `/orbital-map?sessionId=demo-1&viewRole=viewer`

## Page démo produit

- **GET `/demo`** : formulaire session, liens MASTER / VIEWER, copie presse-papiers, test WebSocket sur la page.

---

## Procédure de validation produit (Redis + 2 workers)

### Prérequis

```bash
pip install -r requirements.txt
```

### 1. Terminal A — Redis

```bash
redis-server
# ou : docker run --rm -p 6379:6379 redis:7-alpine
```

### 2. Terminal B — AstroScan avec Redis et 2 workers

Adapter le chemin et le module WSGI réel du projet (souvent `station_web:app`).

```bash
export REDIS_URL="redis://127.0.0.1:6379/0"
cd /chemin/vers/astro_scan
gunicorn -w 2 -b 0.0.0.0:5000 --timeout 120 station_web:app
```

> **Note :** le support WebSocket sous Gunicorn dépend du worker class (ex. `gevent` / `eventlet`). Pour un test **minimal** du hub Redis, on peut valider d’abord avec **un seul worker** + Redis (diffusion Redis + persistance + master lock), puis passer à 2 workers avec une stack WS adaptée.

### 3. Navigateur

1. Ouvrir **`/demo`**, définir un `sessionId`, ouvrir **MASTER** et **VIEWER** (deux appareils ou deux navigateurs).
2. Vérifier les logs serveur :
   - premier master : `VIEW_SYNC: MASTER ACCEPTED`
   - second master même session : `VIEW_SYNC: MASTER DOWNGRADED`
3. Cas à valider :
   - synchro caméra / filtres / sélection (MASTER → VIEWER) ;
   - VIEWER connecté **après** : réception **init state** (`VIEW_SYNC: init state envoyé`) ;
   - coupure WS puis reconnexion : état repris via init + mises à jour ;
   - pas de boucle : VIEWER n’émet pas (`VIEW_STATE ignoré` si tentative).

### 4. Sans Redis (régression locale)

```bash
unset REDIS_URL
python3 station_web.py   # ou votre lanceur habituel
```

Log attendu : `VIEW_SYNC: Redis indisponible (REDIS_URL absent) — mode local mono-processus.`

## Dépendance Python

Le paquet `redis` est listé dans `requirements.txt`.
