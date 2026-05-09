# Note de session — 8 mai 2026 soir

## Accomplissements
- PASS 27.2 ✓ — Extraction TLE worker vers app/workers/tle_worker.py
  - 4 fonctions + 15 constantes/globals déplacées (cycle-safe)
  - Strangler fig : re-export depuis station_web.py (imports legacy préservés)
  - station_web.py : 3766 → 3362 lignes (-404, -10.7%)
  - tle_worker.py : 508 lignes, modulaire, testable

## Métriques
- Endpoints : 14/14 → 200
- Régressions : 0
- Service redémarré : 195 MB RAM, stable
- TLE_CACHE : 1000 items, identity-stable préservée

## État laissé
- Commit HEAD : 4d909f9 [PASS 27.2]
- Branche : ui/portail-refactor-phase-a
- Pushé sur origin : OUI
- Production stable, fallback opérationnel

## Tags rollback
- pass27_2-pre  → état avant extraction
- pass27_2-done → état après extraction (HEAD)

## Observations (non-bloquantes)
- /api/sdr/passes encore 12s (NOAA-15/18/19 absents Celestrak — KNOWN_ISSUE)
- /apod premier hit 10.5s (cache miss post-restart, normal)

## Prochaines pistes possibles
1. PASS 27.3 — Extraction NASA APOD/Stellarium helpers vers app/services/
2. Mini-PASS — graceful degradation /api/sdr/passes (skip TLE manquants)
3. Mini-PASS — fallback cache /api/apod (KNOWN_ISSUES documenté)
