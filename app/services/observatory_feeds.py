"""Observatory feeds — JWST images (NASA Images API + Claude descriptions).

Extrait de station_web.py (PASS 10) pour permettre l'utilisation
par ai_bp (routes /api/jwst/*) sans dépendance circulaire.

Cache fichier 6h dans data/jwst_cache.json.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import List

from app.config import STATION
from app.services.http_client import _curl_get
from app.services.ai_translate import _call_claude

log = logging.getLogger(__name__)

_JWST_CACHE_FILE = f"{STATION}/data/jwst_cache.json"
_JWST_CACHE_TTL = 21600  # 6 heures

_JWST_STATIC: List[dict] = [
    {
        "title": "Pillars of Creation — NIRCam",
        "url": "https://stsci-opo.org/STScI-01GA6KKWG5388N7P9NWJGQFQ3E.png",
        "date": "2022-10-19",
        "credits": "NASA/ESA/CSA JWST · STScI",
        "description": (
            "Les Piliers de la Création photographiés par le NIRCam de JWST révèlent "
            "des colonnes de gaz et de poussière interstellaire où naissent de nouvelles "
            "étoiles dans la nébuleuse de l'Aigle (M16). Cette image infrarouge perce les "
            "voiles de poussière et expose des milliers d'étoiles en formation jamais "
            "visibles auparavant."
        ),
    },
    {
        "title": "Carina Nebula — NIRCam",
        "url": "https://stsci-opo.org/STScI-01G7ETPF7T11KYRNMQXFD9YHHK.png",
        "date": "2022-07-12",
        "credits": "NASA/ESA/CSA JWST · STScI",
        "description": (
            "La Nébuleuse de la Carène vue par JWST en infrarouge proche dévoile des "
            "centaines de proto-étoiles et d'étoiles jeunes enfouies dans les nuages de "
            "gaz moléculaires. Cette région de formation stellaire intense, située à "
            "7 600 années-lumière, révèle pour la première fois les contours précis des "
            "«falaises cosmiques» d'où émergent de nouvelles étoiles."
        ),
    },
    {
        "title": "SMACS 0723 — Premier champ profond",
        "url": "https://stsci-opo.org/STScI-01G77PKB8NKR7S8Z3HN3KVTF21.png",
        "date": "2022-07-12",
        "credits": "NASA/ESA/CSA JWST · STScI",
        "description": (
            "Le premier champ profond de JWST centré sur l'amas de galaxies SMACS 0723 "
            "montre des milliers de galaxies sur un timbre-poste de ciel. La gravité de "
            "l'amas agit comme une lentille gravitationnelle qui amplifie et déforme la "
            "lumière de galaxies encore plus lointaines, certaines vieilles de plus de "
            "13 milliards d'années."
        ),
    },
    {
        "title": "Stephan's Quintet — NIRCam+MIRI",
        "url": "https://stsci-opo.org/STScI-01G7QAGTDMTB1RYQE9P5AXH3HZ.png",
        "date": "2022-07-12",
        "credits": "NASA/ESA/CSA JWST · STScI",
        "description": (
            "Le Quintette de Stephan, premier groupe compact de galaxies découvert, "
            "montre quatre des cinq galaxies en interaction gravitationnelle intense "
            "dans cette mosaïque JWST de 150 millions de pixels. Les ondes de choc "
            "issues des collisions galactiques et les flots de gaz sont clairement "
            "visibles, offrant une fenêtre unique sur l'évolution des galaxies."
        ),
    },
    {
        "title": "Southern Ring Nebula — NIRCam",
        "url": "https://stsci-opo.org/STScI-01G6DCYD09HESZR8CNAQFWCN3K.png",
        "date": "2022-07-12",
        "credits": "NASA/ESA/CSA JWST · STScI",
        "description": (
            "La Nébuleuse de l'Anneau du Sud (NGC 3132) révèle une étoile mourante en "
            "train d'expulser ses couches externes dans l'espace. JWST identifie "
            "clairement l'étoile blanche centrale responsable des anneaux de gaz "
            "lumineux, dévoilant la structure complexe de cette nébuleuse planétaire "
            "située à 2 000 années-lumière dans la constellation des Voiles."
        ),
    },
    {
        "title": "Tarantula Nebula — NIRCam",
        "url": "https://stsci-opo.org/STScI-01GE6XCSMFB1XHZS8ZJNRKX0WN.png",
        "date": "2022-09-06",
        "credits": "NASA/ESA/CSA JWST · STScI",
        "description": (
            "La Nébuleuse de la Tarentule (30 Doradus), région de formation stellaire "
            "la plus active et lumineuse des galaxies satellites de la Voie Lactée, est "
            "photographiée ici par JWST. Les filaments de gaz ionisé entourent des amas "
            "d'étoiles massives ultra-brillantes dont les vents stellaires sculptent les "
            "cavités de la nébuleuse."
        ),
    },
]


def fetch_jwst_live_images() -> List[dict]:
    """Fetch JWST images: NASA images API → file cache → static fallback."""
    # 1. File cache (6h)
    try:
        if os.path.exists(_JWST_CACHE_FILE):
            age = time.time() - os.path.getmtime(_JWST_CACHE_FILE)
            if age < _JWST_CACHE_TTL:
                with open(_JWST_CACHE_FILE, "r") as f:
                    cached = json.load(f)
                    if cached:
                        return cached
    except Exception:
        pass

    imgs: List[dict] = []

    # 2. NASA Images API — JWST science images (post-launch 2022+)
    try:
        raw = _curl_get(
            "https://images-api.nasa.gov/search?q=webb+telescope+nebula+galaxy"
            "&media_type=image&year_start=2022",
            timeout=12,
        )
        if raw:
            data = json.loads(raw)
            items = data.get("collection", {}).get("items", [])
            science_imgs = []
            for item in items:
                meta = item.get("data", [{}])[0]
                links = item.get("links", [{}])
                img_url = links[0].get("href", "") if links else ""
                date = (meta.get("date_created") or "")[:10]
                if img_url and meta.get("title") and date >= "2022-07-01":
                    science_imgs.append({
                        "title": meta.get("title", "JWST Image"),
                        "url": img_url,
                        "date": date,
                        "credits": "NASA/ESA/CSA JWST",
                        "description": "",
                    })
                if len(science_imgs) >= 6:
                    break
            if len(science_imgs) >= 4:
                imgs = science_imgs
    except Exception:
        pass

    # Use static if live results insufficient
    if len(imgs) < 4:
        imgs = list(_JWST_STATIC)

    # 3. Claude AI analysis for each image (up to 4)
    for img in imgs[:4]:
        if img.get("description"):
            continue
        try:
            prompt = (
                f"En exactement 2 phrases en français (sans titre, sans markdown, sans numérotation), "
                f"décris scientifiquement l'image JWST intitulée '{img['title']}' ({img.get('date', '')}) "
                f"pour un public passionné d'astronomie. Commence directement par la description."
            )
            desc, err = _call_claude(prompt)
            if desc and not err:
                lines = [l for l in desc.strip().split("\n") if l.strip() and not l.startswith("#")]
                img["description"] = " ".join(lines).strip()
        except Exception:
            pass

    # 4. Save to file cache
    try:
        os.makedirs(os.path.dirname(_JWST_CACHE_FILE), exist_ok=True)
        with open(_JWST_CACHE_FILE, "w") as f:
            json.dump(imgs, f)
    except Exception:
        pass

    return imgs


def jwst_cache_file_path() -> str:
    return _JWST_CACHE_FILE
