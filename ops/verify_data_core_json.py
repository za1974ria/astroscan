#!/usr/bin/env python3
"""
Validation défensive des JSON sous data_core/ — lecture seule, aucune écriture.
Sortie : code 0 si tous les .json testés sont parseables, 1 sinon.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_CORE = ROOT / "data_core"


def main() -> int:
    if not DATA_CORE.is_dir():
        print("SKIP: data_core absent")
        return 0
    errors = []
    for path in sorted(DATA_CORE.rglob("*.json")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            json.loads(raw)
            print(f"OK  {path.relative_to(ROOT)}")
        except Exception as e:
            msg = f"BAD {path.relative_to(ROOT)}: {e}"
            print(msg)
            errors.append(msg)
    if errors:
        print(f"\nÉchecs: {len(errors)}", file=sys.stderr)
        return 1
    print("Tous les JSON data_core testés: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
