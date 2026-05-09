# Rapport détaillé — ASTRO-SCAN / ORBITAL-CHOHRA

**Date du rapport :** 9 mars 2026  
**Station :** Hillsboro (Oregon, USA) · IP 5.78.153.17  
**Directeur :** Zakaria Chohra (Tlemcen, Algérie)

---

## 1. Vue d’ensemble

**ASTRO-SCAN** (marque **ORBITAL-CHOHRA**) est une station d’analyse astronomique qui agrège des images et métadonnées de plusieurs sources (NASA APOD, ESA Hubble, bases MAST, SDR/NOAA, etc.), les analyse via l’IA **AEGIS** (Gemini), et expose le tout via une application web type “mission control” (portail, dashboard, galerie, observatoire, vision 2026) avec PWA, traduction FR/EN et suivi ISS.

---

## 2. Architecture technique

### 2.1 Stack

| Composant        | Technologie                          |
|------------------|--------------------------------------|
| Backend          | Python 3, Flask                      |
| Base de données  | SQLite (`archive_stellaire.db`)      |
| IA / Traduction | Google Gemini (2.0-flash, 2.5-flash)|
| Frontend         | HTML/CSS/JS, templates Jinja2       |
| PWA              | Service Worker, manifest.json        |
| Déploiement      | systemd (`astroscan-web.service`)    |

### 2.2 Arborescence principale

```
/root/astro_scan/
├── station_web.py          # Application Flask (552 lignes)
├── nasa_feeder.py          # Alimentation images NASA/ESA (82 lignes)
├── pretranslate.py         # Traduction batch EN→FR (Gemini)
├── .env                     # Clés API (NASA, Gemini)
├── manifest.json            # PWA
├── sw.js                    # Service Worker (cache orbital-v3)
├── templates/
│   ├── portail.html         # Portail principal (948 lignes)
│   ├── index.html           # Dashboard QG (868 lignes)
│   ├── overlord_live.html   # Centre de contrôle (956 lignes)
│   ├── galerie.html         # Archive stellaire (392 lignes)
│   ├── observatoire.html    # Observatoire mondial (490 lignes)
│   ├── vision.html          # Vision 2026 (644 lignes)
│   └── _frame.html          # Frame commun (16 lignes)
├── static/
│   └── img/                 # Icônes PWA (192, 512)
├── data/
│   ├── archive_stellaire.db # Base observations
│   ├── telescope_hub.json   # État des télescopes
│   ├── sdr_status.json      # État pipeline SDR/NOAA
│   ├── shield_status.json   # (optionnel)
│   └── 2026-03-08/, 2026-03-09/  # Rapports par jour
├── telescope_live/
│   ├── current_live.jpg     # Image live affichée
│   ├── current_title.txt   # Titre courant
│   └── live_report.txt     # Rapport texte
└── logs/
    ├── web.log
    ├── apod.log
    ├── moisson.log
    ├── sdr_pipeline.log
    ├── telescope_hub.log
    ├── iss_tracker.log
    ├── eye_of_aegis.log
    ├── translate.log
    └── astro.log
```

---

## 3. Base de données

### 3.1 Table `observations`

| Colonne           | Type    | Description                          |
|-------------------|--------|--------------------------------------|
| id                | INTEGER | Clé primaire auto-incrémentée      |
| timestamp         | TEXT    | Date/heure de l’observation         |
| image_path        | TEXT    | Chemin image (optionnel)             |
| source            | TEXT    | Ex. NASA APOD, ESA Hubble, SDR/NOAA |
| analyse_gemini    | TEXT    | Rapport d’analyse IA (EN)           |
| rapport_fr        | TEXT    | Traduction FR (cache)                |
| objets_detectes   | TEXT    | Type d’objet (classification)       |
| anomalie         | INTEGER | 0/1 flag anomalie                    |
| score_confiance   | REAL    | Score de confiance                   |
| title             | TEXT    | Titre de l’observation               |

### 3.2 Requêtes principales

- Dernières observations : `ORDER BY id DESC LIMIT 20` avec traduction FR si `lang=fr`.
- Stats : `COUNT(*)`, `COUNT(anomalie=1)`, `COUNT(DISTINCT source)`, requêtes du jour.
- Galerie : 100 dernières observations + stats par `objets_detectes`.
- SDR/NOAA : filtrage `source LIKE '%SDR%' OR '%NOAA%'`.
- MAST/Hubble/JWST : filtrage sur `source` pour cibles MAST.

---

## 4. Application web (Flask)

### 4.1 Routes pages (HTML)

| Route            | Template            | Rôle                              |
|------------------|---------------------|-----------------------------------|
| `/`              | —                   | Redirection vers `/portail`       |
| `/portail`       | portail.html        | Portail principal (accueil)       |
| `/dashboard`     | index.html          | Dashboard QG                       |
| `/overlord_live` | overlord_live.html  | Centre de contrôle (Overlord)     |
| `/galerie`       | galerie.html        | Archive stellaire (liste + stats)  |
| `/observatoire`  | observatoire.html   | Carte / hub télescopes             |
| `/vision`        | vision.html         | Vision 2026 (roadmap)             |

La route `/galerie` injecte en plus : `stats`, `observations`, `classification_stats`.

### 4.2 API REST

**Données principales**

- `GET /api/latest?lang=fr|en` — Dernières observations, total, anomalies, sources, req_jour, avec traduction FR si demandée.
- `GET /api/image` — Image live (`current_live.jpg`) ou placeholder PNG 1×1.
- `GET /api/title` — Titre et source de l’observation courante.

**ISS**

- `GET /api/iss` — Position ISS (lat, lon, alt, speed, region) via open-notify et wheretheiss.at.

**AEGIS / Chat**

- `POST /api/chat` — Chat avec AEGIS (Gemini 2.5-flash), contexte station injecté.
- `POST /api/translate` — Traduction d’un texte EN→FR (Gemini 2.0-flash).

**Télescopes / Hub**

- `GET /api/telescope-hub` — Liste télescopes (fichier JSON ou fallback statique : NASA SkyView, SIMBAD, ESA Hubble, Chandra, IRSA/WISE, MPC).

**Sécurité / statut**

- `GET /api/shield` — Statut “shield” (fichier JSON ou défaut actif).

**Classification / MAST**

- `GET /api/classification/stats` — Effectifs par type d’objet (attention : voir point 6.1).
- `GET /api/mast/targets` — Cibles MAST/Hubble/JWST.

**SDR**

- `GET /api/sdr/status` — Statut pipeline SDR (fichier `sdr_status.json`).
- `GET /api/sdr/stations` — Liste stations SDR (Twente, Rome, Bordeaux, Madrid).
- `GET /api/sdr/captures` — Dernières captures SDR/NOAA.

**PWA / santé**

- `GET /sw.js` — Service Worker.
- `GET /manifest.json` — Manifest PWA (ou généré par Flask).
- `POST /api/push/subscribe` — Souscription push (stub).
- `GET /api/health` — Health check (station, time UTC).

**Static**

- `GET /static/<path>` — Fichiers statiques.

---

## 5. Portail (portail.html)

- **Sidebar :** navigation (Accueil, Dashboard, Overlord, Galerie, Observatoire, Vision 2026), bloc **ISS Live** (canvas globe + lat/lon/alt/speed/région), AEGIS (REQ/JOUR, barre), **Stats Live** (observations, anomalies, sources), infos station.
- **Topbar :** marque ASTRO-SCAN · ORBITAL-CHOHRA, indicateurs AEGIS/WEB/NASA, **sélecteur FR/EN**, horaire UTC, Hillsboro · IP.
- **Zone centrale :** splash (logo, boutons vers chaque section), **iframes en lazy-load** (`data-src`) pour Dashboard, Overlord, Galerie, Observatoire, Vision.
- **Mobile :** bouton **SYNC** (purge caches + unregister SW + reload), sidebar adaptée, ISS masqué sous 900px.
- **i18n :** libellés en `data-i18n`, dictionnaires FR/EN en JS, langue persistée en `localStorage`.

---

## 6. Alimentation et traitements

### 6.1 NASA Feeder (`nasa_feeder.py`)

- **NASA APOD** : image du jour (API NASA, clé `.env`).
- **APOD Archive** : tirage aléatoire année 2015–2024.
- **ESA Hubble** : liste d’URLs fixes (Piliers de la Création, M51, Carène, M31, etc.), une choisie au hasard.
- Écriture dans `telescope_live/` : `current_live.jpg`, `current_title.txt`.
- Boucle infinie avec rotation des sources (APOD, archive, ESA x2).

### 6.2 Traduction

- **À la volée :** dans `api_latest`, si `lang=fr` et pas de cache `rapport_fr`, appel à `_gemini_translate()` (Gemini 2.0-flash) et mise à jour de `rapport_fr` en base.
- **Batch :** `pretranslate.py` — sélection des observations sans `rapport_fr` et avec `analyse_gemini` suffisamment long, traduction par Gemini puis mise à jour en base (limite 500, throttle 0,5 s).

### 6.3 Données externes

- **ISS :** open-notify.org et wheretheiss.at (fallback).
- **Telescope Hub :** fichier `data/telescope_hub.json` (âge < 1 h) avec télescopes (ESA Hubble, SIMBAD, NASA SkyView, etc.), sinon fallback statique.
- **SDR :** `data/sdr_status.json` (statut, prochain passage NOAA, station, fréquence, etc.).

---

## 7. PWA et Service Worker

- **Manifest :** nom ORBITAL-CHOHRA / ASTRO-SCAN, `start_url` `/portail`, thème `#00d4ff`, fond `#010408`, icônes 192 et 512.
- **SW :** cache `orbital-v3`, mise en cache de `/`, `/portail`, `/dashboard`. Routes `/api/*` toujours en réseau (no-store). Stratégie cache-first avec mise à jour en arrière-plan.

---

## 8. Déploiement (systemd)

- **Service :** `astroscan-web.service`
- **WorkingDirectory :** `/root/astro_scan`
- **ExecStart :** `/usr/bin/python3 /root/astro_scan/station_web.py`
- **EnvironmentFile :** `-/root/astro_scan/.env`
- **Restart :** always, RestartSec=5

Le serveur Flask écoute sur `0.0.0.0:5000` (à mettre derrière un reverse proxy en production si besoin).

---

## 9. Points d’attention et correctifs suggérés

### 9.1 API `/api/classification/stats`

La route utilise les colonnes `type_objet` en SELECT et GROUP BY, alors que la table `observations` contient `objets_detectes`. Il faut aligner sur la base réelle, par exemple :

- `COALESCE(objets_detectes,'inconnu') as type` et `GROUP BY objets_detectes`.

Sans cela, l’endpoint peut échouer ou ne pas refléter les données.

### 9.2 Sécurité

- Ne pas exposer de clés API dans le front.
- En production : HTTPS, reverse proxy (nginx/Caddy), limitation de débit sur `/api/chat` et `/api/translate` (coût Gemini).

### 9.3 Logs

- Les logs (web, apod, moisson, sdr, telescope_hub, iss, translate, astro) sont dans `logs/`. Prévoir une rotation (logrotate) pour éviter une croissance illimitée.

---

## 10. Résumé chiffré

| Élément              | Valeur / description                    |
|----------------------|----------------------------------------|
| Fichiers templates   | 7 (dont portail 948 lignes)            |
| Lignes backend       | 552 (station_web) + 82 (nasa_feeder)    |
| Routes HTTP          | 6 pages + 1 redirect                    |
| Endpoints API        | 18+ (latest, image, title, iss, chat, translate, telescope-hub, shield, classification/stats, mast/targets, sdr/*, health, static, sw, manifest, push) |
| Table principale     | observations (10 colonnes)              |
| Sources d’images     | NASA APOD, APOD Archive, ESA Hubble    |
| Langues UI           | FR, EN (portail et labels)             |
| PWA                  | Oui (manifest + Service Worker)        |

---

*Rapport généré pour la station ASTRO-SCAN / ORBITAL-CHOHRA.*
