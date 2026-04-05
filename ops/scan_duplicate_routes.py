#!/usr/bin/env python3
"""Liste les chemins @app.route(...) apparaissant sur plusieurs lignes dans station_web.py."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "station_web.py"


def main() -> None:
    text = WEB.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    by_path: dict[str, list[int]] = defaultdict(list)
    for i, line in enumerate(lines, 1):
        m = re.search(r"@app\.route\(\s*['\"]([^'\"]+)['\"]", line)
        if m:
            by_path[m.group(1)].append(i)
    dups = {p: nums for p, nums in by_path.items() if len(nums) > 1}
    if not dups:
        print("Aucun chemin @app.route dupliqué (même chaîne, lignes multiples).")
        return
    for p in sorted(dups):
        print(f"{p!r} -> lignes {dups[p]}")


if __name__ == "__main__":
    main()
