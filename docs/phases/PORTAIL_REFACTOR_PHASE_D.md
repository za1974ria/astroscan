# PORTAIL REFACTOR — PHASE D

**Date :** 2026-05-07  
**Branche :** `ui/portail-refactor-phase-a`

| FIX | Commit | Tag |
|---|---|---|
| D1 dead-zone canvas | `d0f4de9` | `ui-phase-d-fix1-done` |
| D2 cards compactés | `8f8e712` | `ui-phase-d-fix2-done` |
| D3 hero compacté | `3c65b61` | `ui-phase-d-fix3-done` |

## D1 — Cause racine
`body::after { position:fixed; top:68px; left:220px; width:310px; height:100vh; background:#07090d; z-index:50 }` — un masque opaque de 310 px peint juste après la sidebar, hérité d'un ancien layout grid. Avec le starfield Canvas (z-index:-1), ce masque cachait les étoiles dans toute la bande. **Retiré entièrement.** `.content-area { z-index:200 }` conservé pour rester au-dessus du canvas.

## D2 — Cartes (.brief-block)
| | Avant | Après |
|---|---|---|
| margin entre cartes | 16 px | **8 px** |
| padding | 10 12 | **8 14** |
| brief-title margin-bottom | 5 px | 3 px |
| brief-desc font-size / line-height | 0.78 / 1.4 | **0.72 / 1.3** |
| meta-note font / margin-top | 0.58 / 6 | **0.55 / 4** + letter-spacing 0.05em |

Hauteur estimée : ~95-105 px (vs ~170-180 px). −45 %.

## D3 — Hero (.portal-hero)
| | Avant | Après |
|---|---|---|
| margin total bottom | 28 + 52 = **80 px** | **16 px** |
| h1 margin-bottom | 10 | 6 |
| p font-size | 17 | 15 |

Hero + 3 cards tiennent désormais dans le 1er viewport 1080p sans scroll. h1 cyan glow préservé.

## Validation
```
curl -sI /portail            → 200 OK
curl -s /portail | grep "body::after\|#07090d"  → 0 (sauf commentaire doc)
systemctl is-active astroscan → active
```

Rollback Phase D : `git reset --hard ui-phase-d-start`.
