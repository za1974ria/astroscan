"""PASS 20.3 (2026-05-08) — Lab/Skyview helpers et constantes.

Extrait depuis station_web.py (L3797-3813 globals + L4041-4071 fonction
_sync_skyview_to_lab) lors de PASS 20.3.

Ce module regroupe les 7 constantes/globals + 1 fonction utilisés par
les blueprints lab_bp et research_bp (qui les importent encore via
``from station_web import …`` lazy à l'intérieur de leurs handlers).

Le shim ``station_web`` ré-exporte les 8 noms depuis ce module pour
préserver la rétro-compat des imports lazy existants.

Note importante sur ``_sync_skyview_to_lab`` :
  La fonction utilise ``HEALTH_STATE``, ``_health_set_error``, ``log`` et
  ``SKYVIEW_DIR`` qui restent définis dans station_web.py. Ces noms sont
  ré-importés via lazy import **à l'intérieur du corps** de la fonction
  pour éviter un cycle d'import au load (station_web charge ce module au
  shim, et ce module ne doit pas tenter d'importer station_web au
  module-level).
"""
from __future__ import annotations

import logging
import os

from app.services.station_state import STATION

log = logging.getLogger(__name__)

# ── Constantes / chemins disques ──────────────────────────────────────
LAB_UPLOADS: str = f'{STATION}/data/lab_uploads'
RAW_IMAGES: str = os.path.join(STATION, "data", "images_espace", "raw")
ANALYSED_IMAGES: str = os.path.join(STATION, "data", "analysed")
MAX_LAB_IMAGE_BYTES: int = 25 * 1024 * 1024  # 25 MB guardrail
METADATA_DB: str = os.path.join(STATION, "data", "metadata")
# Espace d'images utilisé par le Lab (compatibilité avec code existant) :
# pointe vers le même répertoire que RAW_IMAGES.
SPACE_IMAGE_DB: str = RAW_IMAGES

# ── État volatile ─────────────────────────────────────────────────────
# Dernier rapport d'analyse Lab (mis à jour par le pipeline d'analyse).
# Mutable dict, conservé identity-stable pour partage in-memory entre
# producteurs (collector) et lecteurs (lab_bp endpoints).
_lab_last_report: dict = {}


def _sync_skyview_to_lab() -> None:
    """Copie les images du dossier SkyView vers RAW_IMAGES et crée les métadonnées lab."""
    import json
    import shutil
    from datetime import datetime

    # Lazy imports pour éviter le cycle station_web ↔ lab_helpers au load.
    # Au moment de l'APPEL (typiquement par un thread après le load complet),
    # station_web est entièrement chargé donc ces noms sont disponibles.
    from station_web import HEALTH_STATE, SKYVIEW_DIR, _health_set_error

    try:
        HEALTH_STATE["collector_status"]["skyview_sync"] = "running"
    except Exception:
        pass
    for file in os.listdir(SKYVIEW_DIR):
        src = os.path.join(SKYVIEW_DIR, file)
        dst = os.path.join(RAW_IMAGES, file)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
                meta = {
                    "source": "SKYVIEW",
                    "telescope": "SkyView Observatory",
                    "filename": file,
                    "date": datetime.utcnow().isoformat() + "Z",
                }
                meta_path = os.path.join(METADATA_DB, file + ".json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception as e:
                log.warning("SkyView sync error %s", e)
                _health_set_error("skyview_sync", e, "warn")
    try:
        HEALTH_STATE["collector_status"]["skyview_sync"] = "ok"
        HEALTH_STATE["skyview_status"] = "ok"
    except Exception:
        pass


__all__ = [
    "LAB_UPLOADS",
    "RAW_IMAGES",
    "ANALYSED_IMAGES",
    "MAX_LAB_IMAGE_BYTES",
    "METADATA_DB",
    "SPACE_IMAGE_DB",
    "_lab_last_report",
    "_sync_skyview_to_lab",
]
