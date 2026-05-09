"""Service tle — TLE parsing, paths, dataset prédiction de passages.

PASS 23 : `get_iss_tle_from_sources`
PASS 2D Cat 2 (2026-05-07) : extraction depuis station_web.py de
  - `TLE_ACTIVE_PATH` (chemin du fichier TLE actif Celestrak)
  - `_parse_tle_file` (parser TLE 3-lines)
  - `_TLE_FOR_PASSES` (jeu de TLE statique pour prédiction de passages)

station_web.py conserve un re-export pour la compat des imports legacy.
"""
import logging
import os

from app.services.station_state import STATION


log = logging.getLogger(__name__)


TLE_DIR = os.path.join(STATION, "data", "tle")
os.makedirs(TLE_DIR, exist_ok=True)
TLE_ACTIVE_PATH = os.path.join(TLE_DIR, "active.tle")


def _parse_tle_file(path, limit=None):
    """Parse un fichier TLE (blocs de 3 lignes: name, line1, line2). Retourne [ { name, line1, line2 }, ... ], max `limit` entries."""
    out = []
    if not path or not os.path.isfile(path):
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip("\r\n") for line in f.readlines()]
        i = 0
        while i + 2 < len(lines) and (limit is None or len(out) < limit):
            name = (lines[i] or "").strip()
            line1 = (lines[i + 1] or "").strip()
            line2 = (lines[i + 2] or "").strip()
            if line1.startswith("1 ") and line2.startswith("2 "):
                out.append({"name": name or "Unknown", "line1": line1, "line2": line2})
            i += 3
    except Exception as e:
        log.warning("parse_tle_file: %s", e)
    return out


# Données TLE pour prédiction de passages (lecture seule, ne pas modifier api/tle/catalog)
_TLE_FOR_PASSES = [
    {"name": "Hubble", "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993", "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"},
    {"name": "NOAA 19", "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996", "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"},
]


def get_iss_tle_from_sources(
    TLE_CACHE,
    TLE_ACTIVE_PATH,
    _parse_tle_file,
    _emit_diag_json,
    os_module,
):
    """Retourne (tle1, tle2) ISS depuis cache mémoire puis fichier complet."""
    try:
        items = (TLE_CACHE or {}).get("items") or []
        for item in items:
            name = str(item.get("name") or "").upper()
            if "ISS" in name or "ZARYA" in name:
                tle1 = str(
                    item.get("line1")
                    or item.get("tle1")
                    or item.get("tle_line1")
                    or ""
                ).strip()
                tle2 = str(
                    item.get("line2")
                    or item.get("tle2")
                    or item.get("tle_line2")
                    or ""
                ).strip()
                if tle1 and tle2:
                    _emit_diag_json(
                        {
                            "event": "iss_tle_loaded",
                            "name": item.get("name"),
                            "tle1_len": len(tle1),
                            "tle2_len": len(tle2),
                        }
                    )
                    return tle1, tle2
    except Exception as e:
        _emit_diag_json(
            {
                "event": "iss_tle_missing",
                "reason": f"exception:{e}",
            }
        )

    try:
        if os_module.path.isfile(TLE_ACTIVE_PATH):
            all_items = _parse_tle_file(TLE_ACTIVE_PATH)
            for item in all_items:
                name = str(item.get("name") or "").upper()
                if "ISS" in name or "ZARYA" in name:
                    tle1 = str(item.get("line1") or "").strip()
                    tle2 = str(item.get("line2") or "").strip()
                    if tle1 and tle2:
                        _emit_diag_json(
                            {
                                "event": "iss_tle_loaded",
                                "name": item.get("name"),
                                "source": "tle_active_file",
                                "tle1_len": len(tle1),
                                "tle2_len": len(tle2),
                            }
                        )
                        return tle1, tle2
    except Exception as e:
        _emit_diag_json(
            {
                "event": "iss_tle_missing",
                "reason": f"file_scan_exception:{e}",
            }
        )

    _emit_diag_json(
        {
            "event": "iss_tle_missing",
            "tle_items_count": len((TLE_CACHE or {}).get("items") or []),
        }
    )
    return None, None
