# Rapport de nettoyage — Architecture AstroScan

*Généré après exécution des instructions Cursor 1 à 5.*

---

## 1. Fichiers Python réellement utilisés

### station_web.py
- **Utilisé** : point d’entrée Flask, toutes les routes et la logique métier.

### Modules importés dans station_web.py (modules/)

| Module | Fichier(s) | Utilisation |
|--------|------------|-------------|
| catalog | `catalog.py` | search_catalog, get_object — /api/catalog, /api/catalog/<id>, /api/v1/catalog |
| observation_planner | `observation_planner.py` | get_tonight_objects, get_moon_phase — /api/tonight, /api/moon, /api/v1/tonight |
| orbit_engine | `orbit_engine.py` | get_iss_precise, get_iss_crew — /api/v1/iss |
| mission_control | `mission_control.py` | get_global_mission_status — /api/mission-control |
| astro_ai | `astro_ai.py` | explain_object — /api/astro/object |
| space_alerts | `space_alerts.py` | get_asteroid_alerts, get_solar_weather — /api/v1/asteroids, /api/alerts/*, /api/v1/solar-weather |
| sondes_module | `sondes_module.py` | get_sondes_payload — /api/sondes |
| live_feeds | `live_feeds.py` | get_spacex_launches, get_space_news, get_mars_weather, get_iss_passes_tlemcen — /api/live/* |
| digital_lab | `digital_lab/` (run_pipeline) | /api/lab/analyze |
| space_analysis_engine | `space_analysis_engine/` | run_analysis, compare_results_from_sources, get_discoveries — /api/analysis/* |
| research_center | `research_center/` | get_research_summary, get_research_events, list_logs — /api/research/* |
| science_archive_engine | `science_archive_engine/` | save_report, list_reports, save_objects, list_objects, save_discovery, list_discoveries, get_archive_index — /api/archive/* |

### Fichiers à la racine du projet (hors modules/)
- **skyview_module.py** : utilisé (import dynamique ou via route skyview).
- **news_module.py** : utilisé pour /api/news.

### Sous-modules non importés directement par station_web.py
- Les sous-fichiers des packages (digital_lab/*.py, space_analysis_engine/*.py, etc.) sont utilisés indirectement via le package (ex. `from modules.digital_lab import run_pipeline` charge le package).

---

## 2. Templates HTML non référencés

### Référencés explicitement (render_template)
- portail.html, research_dashboard.html, overlord_live.html, galerie.html, observatoire.html, vision.html, vision_2026.html, sondes.html, scientific.html, ce_soir.html, mission_control.html, telescopes.html, globe.html, lab.html, research.html, space.html, research_center.html.

### Référencés dynamiquement (/module/<name>)
- Tout fichier `{name}.html` présent dans `templates/` peut être servi (ex. dashboard.html via /module/dashboard).

### Non référencés (orphelins)
| Template | Remarque |
|----------|----------|
| **index.html** | Jamais utilisé dans station_web.py (la route / renvoie vers /observatoire, /dashboard vers research_dashboard.html). |
| **_frame.html** | Jamais passé à render_template. |
| **module_not_ready.html** | Non utilisé ; la route /module/<name> renvoie du HTML inline si le template n’existe pas. |
| **observatoire_mediocre.html** | Jamais utilisé. |
| **observatoire_live.html** | Jamais utilisé. |
| **observatoire_50ko.html** | Jamais utilisé. |

**Recommandation** : conserver pour l’instant (variantes / démo) ou les déplacer dans un dossier `templates/_archives/` si vous souhaitez alléger la liste sans les supprimer.

---

## 3. Modules Python non importés

- Tous les modules listés en section 1 sont importés par station_web.py.
- **Aucun** fichier `.py` dans `modules/` n’est totalement orphelin si le package est importé (les sous-modules sont chargés par le package).
- Fichiers à la racine non utilisés : à vérifier manuellement (ex. scripts one-shot, anciens scripts). `skyview_module` et `news_module` sont utilisés.

---

## 4. APIs référencées par le frontend

APIs appelées depuis les templates (fetch ou lien) :

- /api/visits, /api/visits/increment  
- /api/iss, /api/latest, /api/telescope/live, /api/image, /api/title  
- /api/sdr/passes, /api/sdr/status, /api/sdr/stations, /api/sdr/captures  
- /api/hubble/images, /api/voyager-live  
- /api/research/summary, /api/research/events, /api/research/logs  
- /api/lab/upload, /api/lab/analyze, /api/lab/report  
- /api/analysis/discoveries, /api/v1/solar-weather, /api/v1/asteroids  
- /api/v1/iss, /api/v1/planets, /api/v1/catalog, /api/v1/tonight  
- /api/moon, /api/tonight, /api/live/spacex, /api/live/news, /api/live/mars-weather, /api/live/iss-passes  
- /api/sondes, /api/dsn  
- /api/skyview/targets, /api/skyview/fetch, /api/skyview/list, /api/skyview/multiwave/<id>  
- /api/chat, /api/astro/explain  
- /api/alerts/all  
- /api/translate  
- /api/archive/reports  
- /api/telescope-hub  

Toutes ces routes existent dans station_web.py. Aucune API définie dans station_web.py n’a été identifiée comme totalement inutilisée par le frontend (certaines peuvent être utilisées par des scripts ou d’autres clients).

---

## 5. Résumé des actions effectuées (Instructions 1–5)

1. **Routes dupliquées** : bloc de 7 routes (api/iss, api/latest, api/sdr/passes, api/sdr/status, api/hubble/images, api/visits, api/voyager-live) supprimé ; les implémentations d’origine sont conservées.
2. **Templates manquants** : research_dashboard.html, vision_2026.html, sondes.html, mission_control.html, globe.html créés (contenu minimal + lien retour portail).
3. **Lien Space Intelligence** : lien /space-intelligence remplacé par /space dans portail.html ; route /space-intelligence ajoutée avec redirect vers /space.
4. **Modules Python** : mission_control.py (get_global_mission_status) et astro_ai.py (explain_object) créés.
5. **Endpoint santé** : /api/system/status ajouté (status, system, version, timestamp, modules).

---

## 6. Nettoyage recommandé (optionnel)

- **Templates orphelins** : index.html, _frame.html, module_not_ready.html, observatoire_mediocre.html, observatoire_live.html, observatoire_50ko.html — à archiver ou supprimer si non utilisés.
- **Vérifier** qu’aucun lien ou iframe ne pointe vers index.html avant suppression.
- **Conserver** tous les modules listés en section 1 ; ne pas supprimer de fichier dans modules/ sans vérifier les imports dans station_web.py et les sous-packages.
