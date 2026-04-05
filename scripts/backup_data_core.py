#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archive additive de data_core/ (zip horodaté) + option SQLite via backup_sqlite.
N’écrase jamais la base source : copie uniquement.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Backup data_core + option DB")
    ap.add_argument("--station", default="/root/astro_scan")
    ap.add_argument("--skip-sqlite", action="store_true", help="Ne pas lancer backup_sqlite")
    args = ap.parse_args()
    station = Path(args.station).resolve()
    core = station / "data_core"
    out_dir = station / "backups" / "data_core_archives"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"mkdir failed: {e}", file=sys.stderr)
        return 2
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zpath = out_dir / f"data_core_{ts}.zip"
    try:
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            if core.is_dir():
                for f in core.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(station))
        print(f"OK {zpath}")
    except Exception as e:
        print(f"zip failed: {e}", file=sys.stderr)
        return 3
    if not args.skip_sqlite:
        try:
            import subprocess

            r = subprocess.run(
                [sys.executable, str(station / "scripts" / "backup_sqlite.py"), "--station", str(station)],
                cwd=str(station),
                timeout=120,
            )
            if r.returncode != 0:
                print("backup_sqlite returned non-zero", file=sys.stderr)
        except Exception as e:
            print(f"backup_sqlite optional run failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
