"""PASS 27.10 (2026-05-09) — Image downloads helpers (NASA APOD, Hubble, JWST, ESA).

Extrait depuis station_web.py L2221-2443 lors de PASS 27.10.

Ce module regroupe les 6 fonctions helper de téléchargement et normalisation
d'images astronomiques pour le pipeline « Lab » (cycle ~horaire piloté par
``app/workers/lab_image_collector.py``) :

- ``log_rejected_image(metadata, reason)`` — log structuré JSON ligne-par-ligne
  des images rejetées dans ``LAB_LOGS_DIR/rejected_images.json``.
- ``save_normalized_metadata(meta_dict)`` — persiste un dict de métadonnées
  normalisé dans ``METADATA_DB/<filename>.json``.
- ``_download_nasa_apod()`` — télécharge l'APOD du jour NASA (1 image),
  rangée dans ``RAW_IMAGES`` avec métadonnées attenantes.
- ``_download_hubble_images()`` — télécharge jusqu'à 5 images du Hubble Space
  Telescope via ``hubblesite.org/api/v3``.
- ``_download_jwst_images()`` — télécharge jusqu'à 3 images JWST récentes via
  ``webbtelescope.org/api/v1/images``.
- ``_download_esa_images()`` — télécharge jusqu'à 4 images « agences spatiales »
  via NASA Images API (``images-api.nasa.gov/search``, repli après obsolescence
  de l'endpoint ``esa.int/api/images`` qui répond 404).

Architecture rappelée :
- Imports directs depuis les modules source (``services.utils._safe_json_loads``,
  ``app.services.station_state.STATION``, ``app.services.lab_helpers.{RAW_IMAGES,
  METADATA_DB}``) — aucun chemin ne repasse par ``station_web``, donc pas de
  cycle, pas besoin de lazy imports vers le monolithe.
- Lazy imports inside conservés pour ``urllib.request`` / ``urllib.parse`` et
  ``datetime as _dt, timezone as _tz`` (pattern original, pas critique mais
  préservé pour fidélité bit-perfect).
- Re-exporté depuis ``station_web.py`` pour préserver le lazy import
  ``from station_web import _download_*`` de ``app/workers/lab_image_collector.py``
  (5 sites d'appel actifs : 4 ``_download_*`` + ``log`` + ``HEALTH_STATE`` +
  ``_health_set_error``).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

from app.services.station_state import STATION
from app.services.lab_helpers import RAW_IMAGES, METADATA_DB
from services.utils import _safe_json_loads

log = logging.getLogger(__name__)

# Calculé localement depuis STATION (cohérent avec station_web.py L2211).
# Pas re-exporté car constante interne à ce module ; station_web conserve sa
# propre copie pour le `os.makedirs(LAB_LOGS_DIR, exist_ok=True)` au boot.
LAB_LOGS_DIR = os.path.join(STATION, "data", "images_espace", "logs")


def log_rejected_image(metadata, reason):
    """Log a rejected laboratory image into a JSON log file."""
    try:
        path = os.path.join(LAB_LOGS_DIR, "rejected_images.json")
        record = {
            "metadata": metadata,
            "reason": reason,
            "timestamp": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        log.warning("log_rejected_image failed: %s", e)


def save_normalized_metadata(meta_dict):
    """Persist a normalized metadata dict to METADATA_DB."""
    try:
        filename = meta_dict.get("local_filename") or meta_dict.get("filename")
        if not filename:
            return
        meta_path = os.path.join(METADATA_DB, str(filename) + ".json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, indent=2)
    except Exception as e:
        log.warning("save_normalized_metadata failed: %s", e)


def _download_nasa_apod():
    """Télécharge l'image du jour NASA APOD vers RAW_IMAGES + métadonnées JSON."""
    import urllib.request
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        url = f"https://api.nasa.gov/planetary/apod?api_key={api_key}&count=1"
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=28) as resp:
            payload = _safe_json_loads(resp.read(), "lab_apod")
            if payload is None:
                return
            data = payload[0] if isinstance(payload, list) and payload else payload
            if not isinstance(data, dict):
                return
            if data.get("url") and data.get("media_type") == "image":
                from datetime import datetime as _dt, timezone as _tz
                img_url = data["url"]
                ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
                safe_date = (data.get("date") or _dt.now(_tz.utc).strftime("%Y-%m-%d")).replace("-", "")
                filename = f"apod_{safe_date}{ext}"
                path = os.path.join(RAW_IMAGES, filename)
                urllib.request.urlretrieve(img_url, path)
                meta = {
                    "source": "NASA APOD",
                    "telescope": "various",
                    "date": data.get("date", ""),
                    "object_name": data.get("title", ""),
                    "filename": filename,
                }
                meta_path = os.path.join(METADATA_DB, filename + ".json")
                with open(meta_path, "w", encoding="utf-8") as fp:
                    json.dump(meta, fp, indent=2)
                saved.append(filename)
    except Exception as e:
        log.debug("download_nasa_apod: %s", e)
    if saved:
        log.info("Lab: saved NASA APOD %s", saved)


def _download_hubble_images():
    """Télécharge un petit lot d'images Hubble vers RAW_IMAGES + métadonnées JSON."""
    import urllib.request
    base_url = "https://hubblesite.org/api/v3"
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        # Limiter le nombre d'images pour rester léger
        index_url = f"{base_url}/images?page=1"
        req = urllib.request.Request(index_url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            images = _safe_json_loads(resp.read(), "lab_hubble_index")
        if not isinstance(images, list):
            return
        # images est une liste de dicts avec au moins un id
        for img in images[:5]:
            img_id = img.get("id")
            if not img_id:
                continue
            detail_url = f"{base_url}/image/{img_id}"
            dreq = urllib.request.Request(detail_url, headers={"User-Agent": "AstroScan-Lab/1.0"})
            with urllib.request.urlopen(dreq, timeout=20) as dresp:
                detail = _safe_json_loads(dresp.read(), "lab_hubble_detail")
            if not isinstance(detail, dict):
                continue
            files = detail.get("image_files") or []
            if not files:
                continue
            # dernier élément = meilleure résolution
            file_url = files[-1].get("file_url")
            if not file_url:
                continue
            filename = f"hubble_{img_id}.jpg"
            path = os.path.join(RAW_IMAGES, filename)
            urllib.request.urlretrieve(file_url, path)
            meta = {
                "source": "HUBBLE",
                "telescope": "HST",
                "date": detail.get("release_date", ""),
                "object_name": detail.get("name", "") or detail.get("mission", ""),
                "filename": filename,
            }
            meta_path = os.path.join(METADATA_DB, filename + ".json")
            with open(meta_path, "w", encoding="utf-8") as fp:
                json.dump(meta, fp, indent=2)
            saved.append(filename)
    except Exception as e:
        log.debug("download_hubble_images: %s", e)
    if saved:
        log.info("Lab: saved Hubble images %s", saved)


def _download_jwst_images():
    """Télécharge des images JWST vers RAW_IMAGES + métadonnées JSON."""
    import urllib.request
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        url = "https://webbtelescope.org/api/v1/images"
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = _safe_json_loads(resp.read(), "lab_jwst")
        if data is None:
            return
        items = data if isinstance(data, list) else (data.get("items", data.get("images", [])) or [])
        for i, item in enumerate(items[:3]):
            img_url = item.get("image_url") or item.get("url") or item.get("file_url") or (item.get("image", {}) or {}).get("url")
            if not img_url:
                continue
            ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
            filename = f"jwst_{int(time.time())}_{i}{ext}"
            path = os.path.join(RAW_IMAGES, filename)
            urllib.request.urlretrieve(img_url, path)
            meta = {
                "source": "JWST",
                "telescope": "James Webb",
                "filename": filename,
            }
            meta_path = os.path.join(METADATA_DB, filename + ".json")
            with open(meta_path, "w", encoding="utf-8") as fp:
                json.dump(meta, fp, indent=2)
            saved.append(filename)
    except Exception as e:
        log.debug("download_jwst_images: %s", e)
    if saved:
        log.info("Lab: saved JWST images %s", saved)


def _download_esa_images():
    """
    Images « agences spatiales » pour le Lab.
    L'endpoint historique esa.int/api/images renvoie 404 — repli NASA Images API (JSON stable).
    """
    import urllib.parse
    import urllib.request
    os.makedirs(RAW_IMAGES, exist_ok=True)
    saved = []
    try:
        q = urllib.parse.quote("satellite mission")
        url = f"https://images-api.nasa.gov/search?q={q}&media_type=image&page_size=10"
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=28) as resp:
            root = _safe_json_loads(resp.read(), "lab_nasa_images")
        if not isinstance(root, dict):
            return
        items = (root.get("collection") or {}).get("items") or []
        for i, it in enumerate(items[:4]):
            if not isinstance(it, dict):
                continue
            img_url = None
            for L in it.get("links") or []:
                if not isinstance(L, dict):
                    continue
                href = (L.get("href") or "").strip()
                if not href:
                    continue
                low = href.lower()
                if any(x in low for x in (".jpg", ".jpeg", ".png", ".webp")):
                    img_url = href
                    break
            if not img_url:
                continue
            ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
            filename = f"esa_{int(time.time())}_{i}{ext}"
            path = os.path.join(RAW_IMAGES, filename)
            try:
                urllib.request.urlretrieve(img_url, path)
            except Exception:
                continue
            meta = {
                "source": "NASA Images (flux Lab agences)",
                "telescope": "multi",
                "filename": filename,
            }
            meta_path = os.path.join(METADATA_DB, filename + ".json")
            with open(meta_path, "w", encoding="utf-8") as fp:
                json.dump(meta, fp, indent=2)
            saved.append(filename)
    except Exception as e:
        log.debug("download_esa_images: %s", e)
    if saved:
        log.info("Lab: saved agency-slot images %s", saved)
