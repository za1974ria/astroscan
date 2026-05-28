# Control Tower — Fork architectural (décision 2026-05-28)

## Contexte

Le module `app/services/control_tower/` existe en **deux versions divergentes**
entre la production (`/opt/astroscan`, déployée le 28/05) et le dépôt
(`/root/astro_scan` + GitHub, HEAD `73b7942`).

Après le grand chantier de réconciliation (commits `984e550` → `0165729` → `73b7942`),
tout `app/` est aligné entre repo et prod **sauf** ces 8 fichiers `control_tower/*`,
qui constituent un fork architectural assumé.

## Les deux versions

| Aspect | PROD (`/opt/astroscan`, déployé) | REPO (`/root/astro_scan`, cible) |
|---|---|---|
| `__init__.py` | vide (0 octets) | 509 octets (exports publics) |
| `classifiers.py` | 2 165 octets (minimal) | **11 896 octets** (étendu) |
| `executor.py` | 3 232 octets | **12 734 octets** |
| `policies.py` | 910 octets | **4 823 octets** |
| `probes.py` | 5 690 octets | **17 263 octets** (probes étendus) |
| `remediator.py` | 1 094 octets | **6 490 octets** |
| `snapshot.py` | 2 365 octets | 6 562 octets |
| `targets.py` | 9 661 octets | 13 639 octets |
| `registry.py` | ❌ absent | ✅ 7 779 octets (registry pluggable) |
| `targets.yaml` | ❌ absent | ✅ 4 193 octets (config externe) |
| **Total** | ~25 KB de code | **~86 KB de code** |
| Statut | éprouvé en prod depuis 2026-05-23 | avancé, **jamais déployé** |

La prod tourne sur une version minimale codée en dur (`targets.py` contient
`TARGETS = [...]` directement). Le repo a une architecture plus ouverte :
config externe YAML chargée par un registry pluggable, probes étendus,
classifiers et remediator plus riches.

Les imports prod (`from app.services.control_tower.snapshot import build_snapshot`,
`from app.services.control_tower.targets import TARGETS`) fonctionnent des deux côtés —
ce sont les **implémentations internes** qui divergent, pas l'API.

Les fichiers `.bak.phase3{b,c,d}*`, `.bak.greypatch*`, `.bak.greyui*`, `.bak.safe20*`
côté prod (jamais nettoyés) tracent l'historique des éditions directes en prod
le 23/05 entre 20h44 et 21h53.

## Décision (2026-05-28)

1. La **version REPO** (avancée, config YAML + registry) est retenue comme **cible
   d'architecture**.
2. Elle **n'est pas déployée en prod immédiatement** : la prod continue de tourner
   sur sa version minimale éprouvée jusqu'à un déploiement validé à froid.
3. **Raison** : à l'approche de l'échéance du 31/05, on ne met pas en prod du code
   non encore éprouvé en conditions réelles. Le design avancé reste prêt dans le
   repo pour un déploiement ultérieur testé.

## Garanties

- AST parse OK sur les 9 fichiers `.py` de la version REPO (vérifié 2026-05-28
  pendant l'audit du fork).
- pytest reste vert (479 passed / 124 skipped) avec la version REPO en place —
  aucun test n'importe explicitement les internals de `control_tower`, donc le
  fork est non régressif côté suite de tests.
- La prod ne lit jamais le repo (`/opt` ≠ `/root`, déploiement séparé) :
  l'existence de ce fork dans le repo n'affecte **pas** le site live.

## Prochaine étape (post-échéance 31/05)

1. Tester la version repo en staging / localement avec `.env` de prod copié en
   lecture seule.
2. Déployer `control_tower/` avec le reste du repo lors du déploiement repo→prod
   global (rsync sélectif, sudo, restart contrôlé).
3. Une fois prod = repo sur ce module, supprimer ce fichier de décision (le fork
   sera clos).

## Bilan réconciliation au 2026-05-28

- 42 fichiers backfillés sur 3 commits (`984e550`, `0165729`, `73b7942`).
- 8 fichiers `control_tower/*` restent divergents — **assumés et documentés ici**.
- Tout le reste de `app/` est désormais aligné entre repo et prod.
