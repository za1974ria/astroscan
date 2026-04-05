#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sauvegarde horodatée de la base SQLite — copie additive, ne supprime pas la source.
Conserve un historique limité de fichiers de backup.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Backup horodaté archive_stellaire.db")
    ap.add_argument(
        "--station",
        default="/root/astro_scan",
        help="Racine du projet AstroScan",
    )
    ap.add_argument(
        "--keep",
        type=int,
        default=12,
        help="Nombre de backups à conserver (les plus anciens supprimés après copie)",
    )
    args = ap.parse_args()
    station = Path(args.station).resolve()
    db = station / "data" / "archive_stellaire.db"
    backup_dir = station / "backups" / "sqlite"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"mkdir failed: {e}", file=sys.stderr)
        return 2
    if not db.is_file():
        print(f"Source missing (skip): {db}", file=sys.stderr)
        return 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"archive_stellaire_{ts}.db"
    try:
        shutil.copy2(db, dest)
        print(f"OK {dest}")
    except Exception as e:
        print(f"copy failed: {e}", file=sys.stderr)
        return 3
    # Rotation : garder les N plus récents par nom (horodatage lexicographique OK)
    try:
        files = sorted(backup_dir.glob("archive_stellaire_*.db"), reverse=True)
        for old in files[args.keep :]:
            try:
                old.unlink()
            except Exception:
                pass
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
