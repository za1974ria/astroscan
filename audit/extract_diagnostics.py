#!/usr/bin/env python3
"""Extraction diagnostics Lighthouse : top pires, problèmes transversaux, plan correction."""
import json
import sys
from pathlib import Path
from collections import defaultdict

reports_dir = Path(sys.argv[1])
issues_count = defaultdict(list)
module_scores = {}

for json_file in sorted(reports_dir.glob("*.json")):
    try:
        with open(json_file) as f:
            data = json.load(f)
        module = json_file.stem
        cats = data.get("categories", {})
        scores = {
            "perf": round((cats.get("performance", {}).get("score") or 0) * 100),
            "a11y": round((cats.get("accessibility", {}).get("score") or 0) * 100),
            "bp": round((cats.get("best-practices", {}).get("score") or 0) * 100),
            "seo": round((cats.get("seo", {}).get("score") or 0) * 100),
        }
        scores["avg"] = sum(scores.values()) / 4
        module_scores[module] = scores

        for audit_id, audit in data.get("audits", {}).items():
            sc = audit.get("score")
            if sc is None or sc >= 1:
                continue
            details = audit.get("details") or {}
            issues_count[audit_id].append({
                "module": module,
                "title": audit.get("title", audit_id),
                "savings_ms": details.get("overallSavingsMs", 0) or 0,
                "savings_bytes": details.get("overallSavingsBytes", 0) or 0,
                "score": sc,
            })
    except Exception as e:
        print(f"<!-- erreur {json_file.name}: {e} -->", file=sys.stderr)

if not module_scores:
    print("# Aucun JSON exploitable")
    sys.exit(0)

print(f"# ASTRO-SCAN — DIAGNOSTICS Lighthouse\n")
print(f"**Modules analysés** : {len(module_scores)}\n")

# TOP 10 pires
print("## 🔴 TOP 10 modules à corriger en priorité (score moyen)\n")
print("| # | Module | Perf | A11y | BP | SEO | Moyenne |")
print("|---|--------|------|------|----|----|---------|")
worst = sorted(module_scores.items(), key=lambda x: x[1]["avg"])[:10]
for i, (mod, sc) in enumerate(worst, 1):
    print(f"| {i} | `{mod}` | {sc['perf']} | {sc['a11y']} | {sc['bp']} | {sc['seo']} | {sc['avg']:.1f} |")

# Modules parfaits
perfect = [m for m, s in module_scores.items()
           if s["perf"] == 100 and s["a11y"] == 100 and s["bp"] == 100 and s["seo"] == 100]
print(f"\n## ✅ Modules à 100/100/100/100 ({len(perfect)}/{len(module_scores)})\n")
if perfect:
    for m in perfect:
        print(f"- `{m}`")
else:
    print("_(aucun pour le moment)_")

# Problèmes transversaux (par catégorie)
print("\n## 🌐 Problèmes transversaux (audits ratés sur ≥ 3 modules)\n")
print("| # | Audit | Modules touchés | Économie ms totale | Économie KiB totale |")
print("|---|-------|-----------------|--------------------|---------------------|")
sorted_issues = sorted(issues_count.items(), key=lambda x: len(x[1]), reverse=True)
filtered = [(k, v) for k, v in sorted_issues if len(v) >= 3]
for i, (issue_id, occ) in enumerate(filtered[:30], 1):
    total_ms = sum(o["savings_ms"] for o in occ)
    total_bytes = sum(o["savings_bytes"] for o in occ)
    title = occ[0]["title"]
    if len(title) > 70:
        title = title[:67] + "..."
    print(f"| {i} | `{issue_id}` — {title} | {len(occ)}/{len(module_scores)} | {total_ms:.0f} | {total_bytes/1024:.0f} |")

# Détail par catégorie
print("\n## 📉 Catégories sous-performantes (modules < 90 par catégorie)\n")
for cat_key, cat_label in [("perf", "Performance"), ("a11y", "Accessibility"),
                            ("bp", "Best Practices"), ("seo", "SEO")]:
    below = [(m, s[cat_key]) for m, s in module_scores.items() if s[cat_key] < 90]
    below.sort(key=lambda x: x[1])
    print(f"### {cat_label}")
    if not below:
        print("- _Tous les modules ≥ 90 ✅_\n")
        continue
    for m, score in below[:15]:
        print(f"- `{m}` : **{score}**")
    print()

# Plan de correction priorisé
print("## 🎯 PLAN DE CORRECTION PRIORISÉ\n")

# Sprint transversal = issues touchant > 50% modules
total = len(module_scores)
sprint_transverse = [(k, v) for k, v in sorted_issues if len(v) > total * 0.5]
print("### Sprint 1 — Corrections transversales (issues touchant > 50% des modules)\n")
if sprint_transverse:
    for issue_id, occ in sprint_transverse[:15]:
        total_ms = sum(o["savings_ms"] for o in occ)
        print(f"- **{issue_id}** : {occ[0]['title']} — `{len(occ)}/{total}` modules, gain potentiel : `{total_ms:.0f} ms`")
else:
    print("_Aucun problème massivement répandu — passer directement aux corrections par module._")

print("\n### Sprint 2 — Modules critiques (avg < 80)\n")
critiques = [(m, s) for m, s in module_scores.items() if s["avg"] < 80]
critiques.sort(key=lambda x: x[1]["avg"])
if critiques:
    for m, s in critiques:
        print(f"- `{m}` (avg `{s['avg']:.1f}`) — P:{s['perf']} A:{s['a11y']} BP:{s['bp']} SEO:{s['seo']}")
else:
    print("_Aucun module sous 80 — passer au Sprint 3._")

print("\n### Sprint 3 — Modules moyens (80 ≤ avg < 95)\n")
moyens = [(m, s) for m, s in module_scores.items() if 80 <= s["avg"] < 95]
moyens.sort(key=lambda x: x[1]["avg"])
if moyens:
    for m, s in moyens:
        deficit = []
        if s["perf"] < 100: deficit.append(f"P:{s['perf']}")
        if s["a11y"] < 100: deficit.append(f"A:{s['a11y']}")
        if s["bp"] < 100: deficit.append(f"BP:{s['bp']}")
        if s["seo"] < 100: deficit.append(f"SEO:{s['seo']}")
        print(f"- `{m}` — {' '.join(deficit)}")

print("\n### Sprint 4 — Finition (95 ≤ avg < 100)\n")
finition = [(m, s) for m, s in module_scores.items() if 95 <= s["avg"] < 100]
finition.sort(key=lambda x: x[1]["avg"])
if finition:
    for m, s in finition:
        deficit = []
        if s["perf"] < 100: deficit.append(f"P:{s['perf']}")
        if s["a11y"] < 100: deficit.append(f"A:{s['a11y']}")
        if s["bp"] < 100: deficit.append(f"BP:{s['bp']}")
        if s["seo"] < 100: deficit.append(f"SEO:{s['seo']}")
        print(f"- `{m}` — {' '.join(deficit)}")

# Recommandation finale
print("\n## 💡 RECOMMANDATION SPRINT À LANCER EN PREMIER\n")
if sprint_transverse:
    top3 = sprint_transverse[:3]
    print("**Sprint 1 (transversal)** — corriger ces audits frappe l'ensemble du parc en une seule passe :")
    for issue_id, occ in top3:
        total_ms = sum(o["savings_ms"] for o in occ)
        total_b = sum(o["savings_bytes"] for o in occ)
        print(f"1. `{issue_id}` → {len(occ)} modules / {total_ms:.0f}ms / {total_b/1024:.0f}KiB")
elif critiques:
    print(f"**Sprint 2 (modules critiques)** — {len(critiques)} modules sous 80, à attaquer en priorité absolue.")
else:
    print("**Sprint 3 ou 4** — pas de problème massif, finition module par module.")
