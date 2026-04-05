# Phase 1 — Audit profond de stabilité (lecture seule)

**Périmètre** : exploitation, configuration, chemins critiques — **aucune modification de code dans ce document.**

## 1. Stabilité serveur

| Élément | Constat |
|---------|---------|
| **systemd `astroscan`** | `Restart=always`, `RestartSec=3`, `TimeoutStopSec=150`, binding **`127.0.0.1:5003`** — bonne isolation réseau. |
| **Gunicorn** | Workers/threads documentés dans l’unit ; risque d’**orphelin** si processus manuel en parallèle (déjà couvert par `deploy/astroscan_reload.sh` `free-port` / `repair`). |
| **Nginx** | Reverse proxy vers loopback — cohérent. |
| **Port 5003** | Écoute **uniquement loopback** (audit récent) — pas d’exposition directe WAN si bind inchangé. |
| **Cycle stop/start** | Arrêt long possible (graceful 120s) ; script `free-port` documenté pour débloquer. |

**Imperfections** : risque **port occupé** après stop incomplet (modéré, procédure existante).

## 2. Stabilité applicative

| Élément | Constat |
|---------|---------|
| **Routes système** | `/api/system-status`, `/api/system-status/cache`, `/api/system-alerts`, `/api/system-heal` (POST), `/api/system-notifications` — toutes avec **try/except** et réponses JSON dégradées en erreur (pas de crash Flask nu). |
| **Route distincte** | `/api/system/status` (orbital) vs `/api/system-status` — **chemins différents**, pas de collision Flask. |
| **Lab** | `/lab/upload` vs `/api/lab/upload` — routes **distinctes** ; pas de doublon de même URL détecté pour les endpoints lab API listés. |
| **Imports** | Moteurs `system_status_engine`, `alert_engine`, `auto_heal_engine`, `notification_engine` chargés **à la volée** dans les handlers — échec import → log + JSON d’erreur. |

**Imperfections critiques** : aucune bloquante identifiée sans exécution runtime étendue.

**Modérées** : dépendance à la **cohérence** des fichiers `data_core/*` (JSON) ; corruption possible → à détecter hors ligne (script dédié).

## 3. Stabilité données (`data_core`)

- Présence typique : `dsn/last_snapshot.json`, `weather/last_weather.json`, `skyview/*.meta.json`, `tle/bundle.json`, logs `alerts` / `notifications`.
- **Risque** : JSON tronqué ou invalide → erreurs dans les moteurs si lecture non défensive partout (à confirmer engine par engine — **pas modifié ici**).
- **Recommandation safe** : script **lecture seule** de validation JSON (ajout `ops/`).

## 4. Stabilité runtime

- Workers Gunicorn rechargés au **restart** systemd — pas de “vieux code” tant que le service est redémarré après déploiement.
- **Divergence** possible si : processus manuel + systemd (déjà documenté dans `astroscan_reload.sh`).

## 5. Stabilité UX (dashboard / portail / landing)

- **dashboard_v2** : dépend de `fetch` vers APIs cache/alerts ; erreur réseau → états dégradés côté JS (pas d’audit destructif des templates dans cette mission).
- **Système** : APIs renvoient JSON même en erreur — UI peut afficher “unknown” / alertes de secours.

## 6. Stabilité sécurité (rappel)

- UFW sans 5003 WAN ; nginx headers sur vhost principal ; fail2ban actif — voir `ops/SECURITY_PHASE1_AUDIT.md`.

---

## Livrable synthèse

### Imperfections critiques (exploitation)
- Aucune **nouvelle** critique bloquante identifiée sans tests de charge réels.

### Imperfections modérées
- Orphelins Gunicorn / port bloqué si arrêt brutal.
- JSON `data_core` potentiellement corrompu (intégrité à surveiller).
- Arrêt systemd pouvant dépasser l’attente utilisateur.

### Améliorations sûres (additifs)
- Scripts `ops/` : healthcheck consolidé, validation JSON `data_core`, détection PIDs sur 5003, rapport unique.
- Documentation restart / rollback sans toucher au code.

### Ne pas toucher (sans analyse métier dédiée)
- `station_web.py` (routes, handlers).
- `templates/` (portail, landing, dashboard_v2).
- Engines `core/*` (logique cache / heal).
- Suppression de fallbacks ou de routes.
