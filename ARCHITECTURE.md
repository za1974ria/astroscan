# ARCHITECTURE TECHNIQUE — ASTRO-SCAN

**Plateforme d'observation astronomique temps réel — Tlemcen, Algérie**

| Champ | Valeur |
|-------|--------|
| **Auteur** | Zakaria Chohra |
| **Domaine** | https://astroscan.space |
| **Localisation serveur** | Hetzner Cloud — Hillsboro, Oregon (US-West) |
| **Spécifications serveur** | CPX31 — x86 — 160 GB |
| **IP publique** | 5.78.153.17 |
| **Coordonnées station** | 34.87°N, 1.32°E (Tlemcen, Algérie) |
| **Version document** | 1.0 — 02/05/2026 |

---

## 1. VUE D'ENSEMBLE

ASTRO-SCAN est une **plateforme d'observation astronomique temps réel** qui agrège, traite et diffuse des données scientifiques issues d'institutions internationales (NASA, ESA, NOAA, CelesTrak, AMSAT) à destination du public, des étudiants et des chercheurs.

La plateforme expose une API publique documentée (OpenAPI 3.0), un visualiseur orbital 3D, un tracker ISS temps réel, des prédictions de passages satellites pour la station de Tlemcen, des analyses IA en français des images APOD de la NASA, et un panneau d'alertes aurores boréales basé sur le Kp index NOAA.

L'architecture suit le **patron modulaire Flask Blueprints** avec ségrégation des responsabilités, validation triangulaire des migrations, backups horodatés systématiques et zéro régression de service sur les 7 migrations successives effectuées le 02/05/2026.

---

## 2. ARCHITECTURE GLOBALE

```
┌──────────────────────────────────────────────────────────────────┐
│                    UTILISATEUR (navigateur)                      │
│              https://astroscan.space (HTTPS Let's Encrypt)       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                     NGINX (reverse proxy)                        │
│           HTTPS termination + static files + caching             │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼ (port 5003)
┌──────────────────────────────────────────────────────────────────┐
│              GUNICORN (4 workers × 4 threads)                    │
│              ─────────────────────────────────                   │
│              FLASK APPLICATION (station_web:app)                 │
│                                                                  │
│   ┌──────────────────────────────────────────────────────┐      │
│   │  COUCHE BLUEPRINTS — Architecture modulaire          │      │
│   │                                                      │      │
│   │  • seo_bp     • apod_bp    • sdr_bp     • iss_bp    │      │
│   │  • i18n_bp    • api_bp     • pages_bp   • main_bp   │      │
│   └──────────────────────────────────────────────────────┘      │
│                                                                  │
│   ┌──────────────────────────────────────────────────────┐      │
│   │  COUCHE SERVICES                                     │      │
│   │  • app/services/satellites.py                        │      │
│   │  • app/services/cache (à venir)                      │      │
│   │  • app/services/tle (à venir)                        │      │
│   │  • app/services/accuracy_history                     │      │
│   └──────────────────────────────────────────────────────┘      │
│                                                                  │
│   ┌──────────────────────────────────────────────────────┐      │
│   │  COUCHE INFRASTRUCTURE                               │      │
│   │  • SQLite (archives stellaires + visiteurs)          │      │
│   │  • Background threads (TLE refresh)                  │      │
│   │  • APScheduler (tâches programmées)                  │      │
│   │  • Watchdog systemd                                  │      │
│   └──────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                  SOURCES EXTERNES SCIENTIFIQUES                  │
│                                                                  │
│  - NASA APIs    : APOD, NEO, DONKI                              │
│  - CelesTrak    : TLE catalog (2514 satellites)                 │
│  - AMSAT        : TLE radio amateur                             │
│  - N2YO         : Predictions satellitaires                     │
│  - NOAA         : Kp index aurores boréales                     │
│  - Open-Notify  : ISS position + crew                           │
│  - Anthropic    : Analyses IA françaises (Claude API)           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. ARCHITECTURE MODULAIRE — BLUEPRINTS FLASK

L'application est organisée en **8 Blueprints** spécialisés, chacun responsable d'un domaine fonctionnel précis. Cette ségrégation permet la maintenance isolée, les tests ciblés, et la scalabilité horizontale future.

| Blueprint   | Routes | Domaine                                | Statut       |
|-------------|--------|----------------------------------------|--------------|
| `seo_bp`    | 3      | SEO, sitemap, robots, meta tags        | Production   |
| `apod_bp`   | 3      | NASA Astronomy Picture of the Day      | Production   |
| `sdr_bp`    | 4      | Software-Defined Radio (NOAA sats)     | Production   |
| `iss_bp`    | 5      | ISS tracker, orbital map, mission ctrl | Production   |
| `i18n_bp`   | 1      | Internationalization (FR/EN)           | Production   |
| `api_bp`    | 2      | Documentation API publique (OpenAPI)   | Production   |
| `pages_bp`  | 2      | Pages statiques (vision, science)      | Production   |
| `main_bp`   | 6      | Entrées principales, /a-propos, /data  | Production   |
| **TOTAL**   | **26** | **Routes modulaires**                  | **8 actifs** |

**Localisation :** `/root/astro_scan/app/blueprints/<name>/`

**Pattern :** `__init__.py` (déclaration `bp`) + `routes.py` (définitions)

**Import dans station_web.py :** `from app.blueprints.<name> import bp as <name>_bp`

---

## 4. STACK TECHNIQUE

### 4.1 Backend

| Composant       | Version    | Justification technique                              |
|-----------------|------------|------------------------------------------------------|
| Python          | 3.12       | Performances, type hints, async natif                |
| Flask           | 3.x        | Léger, modulaire, Blueprints natifs                  |
| Gunicorn        | 20.1.0     | Serveur WSGI production, workers + threads           |
| systemd         | -          | Gestion service + watchdog automatique               |
| nginx           | -          | Reverse proxy, HTTPS, static files                   |
| SQLite          | 3.x        | DB embarquée, archives stellaires + analytics       |
| APScheduler     | -          | Tâches programmées (refresh données)                 |

### 4.2 Bibliothèques scientifiques

| Bibliothèque    | Usage                                                |
|-----------------|------------------------------------------------------|
| `skyfield`      | Propagation orbitale SGP4 haute précision            |
| `sgp4`          | Calculs orbitaux NORAD (TLE)                         |
| `astropy`       | Éphémérides, conversions de coordonnées              |
| `geoip2`        | Géolocalisation des visiteurs (124.9 MB DB locale)   |

### 4.3 Sécurité & déploiement

- **HTTPS** : Let's Encrypt via certbot-dns-porkbun
- **Domaine** : astroscan.space (Porkbun, $1.96/an)
- **Backup domaine** : orbital-chohra-dz.duckdns.org
- **Serveur** : Hetzner Cloud, Hillsboro Oregon (5.78.153.17, CPX31, x86, 160 GB)
- **Sauvegardes** : Backups horodatés systématiques avant chaque modification

---

## 5. PIPELINE DE DONNÉES

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  SOURCES NASA   │────▶│   CACHE LAYER   │────▶│   API PUBLIQUE  │
│   ESA / NOAA    │     │  (refresh auto) │     │  (JSON / HTML)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                        │
        │                       ▼                        │
        │              ┌─────────────────┐               │
        │              │  TRAITEMENT IA  │               │
        │              │   Claude API    │               │
        │              │ (FR translation)│               │
        │              └─────────────────┘               │
        │                       │                        │
        ▼                       ▼                        ▼
┌──────────────────────────────────────────────────────────────┐
│              UTILISATEUR FINAL (navigateur)                  │
│  - Visualisation 3D Cesium    - Graphiques Chart.js          │
│  - Tracker ISS temps réel     - Aurores boréales Kp NOAA     │
│  - APOD français analysé IA   - Panneau JWST                 │
└──────────────────────────────────────────────────────────────┘
```

### Sources de données scientifiques certifiées

1. **NASA APOD** : Image astronomique du jour + analyse IA française
2. **CelesTrak** : 2514 satellites TLE (mise à jour automatique)
3. **AMSAT** : TLE satellites radio amateur
4. **NOAA** : Kp index pour prédictions aurores boréales (Tlemcen)
5. **Open-Notify** : Position ISS temps réel + équipage
6. **N2YO** : Prédictions de passages satellitaires
7. **wheretheiss.at** : Stream SSE position ISS

---

## 6. INFRASTRUCTURE DE FIABILITÉ

### 6.1 Watchdog systemd

Service `astroscan-watchdog.service` qui surveille en permanence l'état d'`astroscan.service` et déclenche un redémarrage automatique en cas de défaillance détectée.

### 6.2 Gestion TLE en background

Thread daemon `tle_refresh_loop` qui rafraîchit le catalogue TLE depuis CelesTrak et AMSAT à intervalles réguliers, garantissant la fraîcheur des prédictions orbitales.

### 6.3 Cache multi-niveaux

- **Cache mémoire** : `TLE_CACHE` partagé (à externaliser en `services/cache_service.py`)
- **Cache fichier** : `data/sdr_status.json`, `data/passages_iss.json`
- **Cache HTTP** : Headers no-cache stratégiques sur routes critiques

### 6.4 Logging structuré

Logs JSON avec champs `event`, `path`, `method`, `status`, `duration_ms` pour analyse automatisée. Détection automatique des `slow_request` (>1s) et `very_slow_request` (>5s).

---

## 7. PROTOCOLE DE MIGRATION & QUALITÉ

### 7.1 Validation triangulaire

Toute modification du code de production suit un **protocole strict en 3 étapes** :

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   PHASE 1   │    │   PHASE 2   │    │   PHASE 3   │
│             │    │             │    │             │
│  Conception │───▶│ Préparation │───▶│ Application │
│             │    │   /tmp/     │    │     prod    │
│             │    │             │    │ (validation │
│             │    │             │    │   humaine)  │
└─────────────┘    └─────────────┘    └─────────────┘
```

### 7.2 Garde-fous techniques

Avant chaque application en production :

- **Backup horodaté** systématique (`station_web.py.bak_<phase>_YYYYMMDD_HHMM`)
- **Validation syntaxique** : `python3 -m py_compile`
- **AST parse** : `ast.parse()` pour détection structure
- **Test d'import** : vérifier les Blueprints avant register
- **Comptage de routes** : invariant strict (aucune route perdue)
- **Détection de collisions URL** : zéro doublon entre Blueprints

### 7.3 Critères de validation post-déploiement

Après chaque restart :

- **`sleep 15`** minimum avant test de statut
- **`systemctl status`** + `journalctl -n 30` lus AVANT toute conclusion
- **11 endpoints critiques** doivent retourner HTTP 200
- **Routes Blueprint nouvellement migrées** doivent retourner 200
- **Aucune trace** de `error|traceback|importerror|exception|critical` dans les logs

### 7.4 Rollback documenté

Chaque migration prévoit une **commande de rollback prête à l'emploi** utilisant les backups horodatés. Procédure testée et documentée dans le journal de refactor.

---

## 8. MESURES DE QUALITÉ — JOURNÉE 1 (02/05/2026)

| Métrique                               | Valeur          |
|----------------------------------------|-----------------|
| Bugs latents corrigés                  | 4               |
| Migrations Blueprint réussies          | 7               |
| Blueprints actifs en production        | 8               |
| Routes modulaires totales              | 26              |
| Régressions de service                 | 0               |
| Pertes de données                      | 0               |
| Backups horodatés                      | 10+             |
| Endpoints critiques validés            | 11/11 (100%)    |
| Disponibilité service                  | 100%            |
| Routes en monolithe restantes          | ~234            |
| Couverture migration                   | ~10%            |

---

## 9. ROADMAP TECHNIQUE

### 9.1 Court terme (sprint en cours)

- Migration des Blueprints simples (B1, B2, B3b, R1, R2, R3) — **TERMINÉ**
- Documentation architecture (ce document) — **EN COURS**
- Pitch deck de présentation
- Démo scriptée 7 minutes

### 9.2 Moyen terme (sprint suivant)

- **B-cache** : Extraction du module cache (`services/cache_service.py`)
  -> Débloque 12 routes ISS en attente
- **B-db** : Extraction du helper `get_db()` (`services/db_service.py`)
  -> Débloque 1 route SDR + 3 routes export
- **B-config** : Centralisation des constantes (`app/config.py`)
- **B-state** : Refonte de `fetch_tle_from_celestrak` (TLE_CACHE global)

### 9.3 Long terme

- Migration vers `create_app()` factory pattern
- Tests automatisés (pytest)
- CI/CD GitHub Actions
- Monitoring Prometheus + Grafana
- API rate limiting
- Containerisation Docker
- Migration BDD vers PostgreSQL

---

## 10. CONTACT & RÉFÉRENCES

**Auteur :** Zakaria Chohra

**Localisation :** Tlemcen, Algérie

**Plateforme :** https://astroscan.space

**Contact technique :** zakaria.chohra@gmail.com

### Sources scientifiques externes

- NASA Open APIs : https://api.nasa.gov
- CelesTrak : https://celestrak.org
- AMSAT : https://amsat.org
- NOAA SWPC : https://swpc.noaa.gov
- ESA : https://esa.int

### Bibliothèques scientifiques utilisées

- Skyfield : https://rhodesmill.org/skyfield
- Astropy : https://astropy.org
- SGP4 : https://pypi.org/project/sgp4

---

*Document généré le 02/05/2026 — Version 1.0*

*ASTRO-SCAN tourne en production 24/7 sur infrastructure Hetzner Cloud (Hillsboro, Oregon), monitoré par watchdog systemd, avec architecture modulaire Flask Blueprints et zéro régression depuis le déploiement initial.*
