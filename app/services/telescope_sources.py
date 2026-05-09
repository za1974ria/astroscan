"""Telescope image sources — APOD live / Hubble archive / APOD archive.

Extrait de station_web.py (PASS 9) pour permettre l'utilisation
par telescope_bp sans dépendance circulaire.

Sources :
    apod         — Image du jour NASA APOD (live)
    hubble       — Image archive ESA/Hubble (sélection aléatoire 6 iconiques)
    apod_archive — APOD aléatoire 2015-2024
"""
from __future__ import annotations

import json
import logging
import os
import random
import urllib.request
from pathlib import Path

from app.config import STATION
from app.services.http_client import _curl_get

log = logging.getLogger(__name__)

_IMAGE_CACHE_TTL = 300  # 5 min — APOD/Hubble/archive changent peu


def _source_path(s: str) -> Path:
    return Path(f"{STATION}/telescope_live/source_{s}.jpg")


def _fetch_apod_live():
    """Image du jour NASA APOD — temps 0 (API en _curl_get, image en urllib pour binaire)."""
    try:
        key = (os.environ.get("NASA_API_KEY") or "DEMO_KEY").strip()
        raw = _curl_get(f"https://api.nasa.gov/planetary/apod?api_key={key}", timeout=14)
        if not raw:
            return None, None, None
        d = json.loads(raw)
        if d.get("media_type") != "image":
            return None, None, None
        url = d.get("hdurl") or d.get("url")
        if not url:
            return None, None, None
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "ORBITAL-CHOHRA/1.0"}),
            timeout=25,
        ) as img:
            data = img.read()
        return data, d.get("title", "APOD"), "NASA APOD"
    except Exception as e:
        log.warning("fetch apod: %s", e)
        return None, None, None


def _fetch_hubble_archive():
    """Image Hubble issue des archives ESA (6 images iconiques, sélection aléatoire).
    Note : images d'archive 1994-2020, pas une observation en cours.
    """
    urls = [
        ("Pilliers de la Création — M16 (1995)", "https://esahubble.org/media/archives/images/screen/heic1501a.jpg"),
        ("Galaxie du Tourbillon M51 (2005)", "https://esahubble.org/media/archives/images/screen/heic0506a.jpg"),
        ("Nébuleuse de la Carène (2007)", "https://esahubble.org/media/archives/images/screen/heic0707a.jpg"),
        ("Galaxie d'Andromède M31 (2015)", "https://esahubble.org/media/archives/images/screen/heic1502a.jpg"),
        ("Nébuleuse Œil de Chat (2004)", "https://esahubble.org/media/archives/images/screen/heic0403a.jpg"),
        ("Jupiter — Grande Tache Rouge (2019)", "https://esahubble.org/media/archives/images/screen/heic1920a.jpg"),
    ]
    title, url = random.choice(urls)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ORBITAL-CHOHRA/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        if len(data) < 10000:
            return None, None, None
        return data, title, "Archives ESA/Hubble"
    except Exception as e:
        log.warning("fetch hubble archive: %s", e)
        return None, None, None


_fetch_hubble_live = _fetch_hubble_archive


def _fetch_apod_archive_live():
    """NASA APOD — image d'archive aléatoire (2015-2024). Pas l'image du jour."""
    try:
        key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        y, m = random.randint(2015, 2024), random.randint(1, 12)
        d = random.randint(1, 28)
        date = f"{y}-{m:02d}-{d:02d}"
        with urllib.request.urlopen(
            f"https://api.nasa.gov/planetary/apod?api_key={key}&date={date}", timeout=12
        ) as r:
            data_j = json.loads(r.read())
        if data_j.get("media_type") != "image":
            return None, None, None
        url = data_j.get("hdurl") or data_j.get("url")
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "ORBITAL-CHOHRA/1.0"}),
            timeout=25,
        ) as img:
            data = img.read()
        return data, data_j.get("title", "APOD") + f" ({date})", f"NASA APOD {date}"
    except Exception as e:
        log.warning("fetch apod archive: %s", e)
        return None, None, None


def fetch_hubble_images():
    """Liste de 6 images Hubble (NASA APOD count=6, fallback statique)."""
    NASA_KEY = (os.environ.get("NASA_API_KEY") or "DEMO_KEY").strip()
    raw = _curl_get(
        f"https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}&count=6", timeout=10
    )
    if raw:
        try:
            items = json.loads(raw)
            imgs = []
            for i in items:
                if i.get("url") and i.get("media_type", "image") == "image":
                    imgs.append({
                        "title": i.get("title", "Hubble"),
                        "url": i.get("hdurl") or i.get("url", ""),
                        "date": i.get("date", ""),
                    })
            if imgs:
                return imgs
        except Exception:
            pass
    return [
        {"title": "Piliers de la Création", "url": "https://apod.nasa.gov/apod/image/2304/M16Pillar_Webb_960.jpg"},
        {"title": "Galaxie du Tourbillon M51", "url": "https://apod.nasa.gov/apod/image/2305/M51_HubbleWebb_960.jpg"},
        {"title": "Nébuleuse de la Carène", "url": "https://apod.nasa.gov/apod/image/2207/Carina_Webb_960.jpg"},
        {"title": "Quintette de Stephan", "url": "https://apod.nasa.gov/apod/image/2207/StephansQuintet_Webb_1024.jpg"},
        {"title": "Galaxie d'Andromède M31", "url": "https://apod.nasa.gov/apod/image/0601/m31_ware_960.jpg"},
        {"title": "Grande Nébuleuse d'Orion M42", "url": "https://apod.nasa.gov/apod/image/2301/M42_Webb_960.jpg"},
    ]
