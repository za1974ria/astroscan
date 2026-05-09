# Rapport PASS 25.5 — Restauration du fallback wsgi.py

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Auteur** : Zakaria Chohra + Claude Opus 4.7 (CTO IA via Claude.ai) + Claude Code (exécution)

---

## Contexte

PASS 25.3 (commit `4cebf53`, 4 mai 2026) avait retiré le bloc `register_blueprint()` historique de `station_web.py`. Justification de l'époque : "target app is dead Flask instance, factory app/__init__.py owns all 23 registrations".

**Conséquence non-anticipée** : le mode fallback documenté dans `wsgi.py` (`ASTROSCAN_FORCE_MONOLITH=1` ou `create_app()` failure) ne servait plus que **1 route** (`/static/<path:filename>`) au lieu des ~290 attendues. Le filet de sécurité du strangler fig pattern était cassé silencieusement depuis le 4 mai.

**Détecté par** : audit témoins du 8 mai matin, mesure runtime via `wsgi.app.url_map.iter_rules()` en mode forcé monolithe.

---

## Solution — Architecture single source of truth

### Modifications

**`app/__init__.py` (+27 lignes, 0 supprimée) :**
Ajout d'une fonction publique `register_all_for_fallback(app: Flask)` qui réutilise les fonctions privées `_register_blueprints` et `_register_hooks` existantes. Pas de duplication de code. Toute évolution future des BPs sera automatiquement propagée au mode fallback.

**`station_web.py` (+26 lignes, 0 supprimée) :**
Ajout d'un bloc try/except après les définitions de routes et avant `if __name__ == '__main__':`. Le bloc importe et appelle `register_all_for_fallback(app)` pour enregistrer tous les BPs/hooks sur `station_web.app`.

### Coût mesuré

- **Mémoire par worker** : +5-10 MB (29 BPs × 2 instances Flask)
- **Démarrage par worker** : +50-150 ms
- **Total mémoire 5 workers** : 194 MB (vs ~150 MB pré-PASS) — confirme l'estimation
- **Lignes ajoutées au monolithe** : +26 (compensé largement par PASS 26 à venir : -322)

---

## Validations effectuées

### Mode normal (production réelle)
- Routes : **293** (pas de régression vs baseline)
- Source : `app` (create_app)
- Workers Gunicorn redémarrés avec le nouveau code

### Mode fallback (`ASTROSCAN_FORCE_MONOLITH=1`)
- Routes : **293** (vs **1** avant PASS 25.5) ← **L'OBJECTIF**
- Source : `station_web` (monolithe)
- Filet de sécurité opérationnel

### Smoke test endpoints (14/14 → HTTP 200)
`/portail` `/observatoire` `/api/health` `/api/weather/archive` `/api/iss` `/api/satellites` `/api/news` `/api/version` `/status` `/api/apod` `/api/system-status` `/api/analytics/summary` `/lab` `/galerie`

### AST + import
- `app/__init__.py` : syntaxe Python valide
- `station_web.py` : syntaxe Python valide
- `from app import register_all_for_fallback` : import OK

### Logs de boot production
Message `[fallback-safety] 293 routes registered on external Flask app` confirmé dans les logs des 5 workers Gunicorn (PIDs 544383, 544386, 544387, 544388, 544389).

---

## Tags git

- `pass25_5-pre` : état avant intervention (sécurité rollback)
- `pass25_5-done` : état après validation runtime complète

## Backups disponibles

`.archive/pass25_5_pre_snapshot/`
- `station_web.py.before_pass25_5` (172 KB)
- `app__init__.py.before_pass25_5` (7.5 KB)

## Procédure de rollback (si jamais nécessaire)

```bash
cd /root/astro_scan
git checkout pass25_5-pre -- station_web.py app/__init__.py
systemctl restart astroscan
```

---

## Audit témoins ASTRO-SCAN — État final 2026-05-08

| # | Témoin | Avant | Après |
|---|---|---|---|
| 1 | Hooks Gunicorn | VERT | VERT |
| 2 | Fallback monolithe | ROUGE | **VERT** |
| 3 | Visitor_log doublon | INDÉTERMINÉ | VERT |
| 4 | Endpoints critiques | INDÉTERMINÉ | VERT |
| 5 | Tracebacks Anthropic | ROUGE | VERT |
| 6 | Routes globales | VERT | VERT |

**6/6 témoins VERT.** Architecture saine, base solide, rollback opérationnel.

---

## Suite recommandée

**PASS 26 — Hooks cleanup** : suppression des hooks dupliqués dans `station_web.py` (zones 305-365, 1279-1447, 3836-3930). Gain attendu : -322 lignes. Désormais réalisable sans risque grâce au filet de sécurité PASS 25.5.

