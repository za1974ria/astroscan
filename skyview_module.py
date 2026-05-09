#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║   SKYVIEW MODULE — NASA Goddard / HEASARC                    ║
║   ORBITAL-CHOHRA / AstroScan-Chohra                          ║
║   ZERO COMPTE · ZERO TOKEN · 100% GRATUIT                    ║
╚══════════════════════════════════════════════════════════════╝

NASA SkyView = service gratuit de NASA Goddard
Retourne des images réelles de n'importe quel objet du ciel
depuis des dizaines de surveys (DSS, 2MASS, GALEX, WISE...)
Aucune inscription requise.

Couche production : core.skyview_engine_safe (cache data_core/skyview/, fallback).
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SKYVIEW")

from core.skyview_engine_safe import get_skyview_safe

SURVEYS = {
    "DSS": "Digitized Sky Survey — optique visible (meilleur pour débutants)",
    "DSS2 Red": "DSS2 Rouge — détail nébuleuses et galaxies",
    "2MASS-K": "Infrarouge proche — perce les nuages de gaz",
    "GALEX Near UV": "Ultraviolet — étoiles chaudes et jeunes",
    "WISE 3.4": "Infrarouge moyen — poussière cosmique",
    "RASS-Int BackgroundMap": "Rayons X — restes de supernovas",
}

TARGETS = {
    "M42": {"name": "Nébuleuse d'Orion", "coords": "83.8221,-5.3911"},
    "M31": {"name": "Galaxie d'Andromède", "coords": "10.6847,41.2691"},
    "M1": {"name": "Nébuleuse du Crabe", "coords": "83.6331,22.0145"},
    "M51": {"name": "Galaxie du Tourbillon", "coords": "202.4696,47.1952"},
    "M57": {"name": "Nébuleuse de la Lyre", "coords": "283.3962,33.0297"},
    "M87": {"name": "M87 — Trou Noir", "coords": "187.7059,12.3911"},
    "M104": {"name": "Galaxie Sombrero", "coords": "189.9978,-11.6231"},
    "M27": {"name": "Nébuleuse Haltère", "coords": "299.9016,22.7211"},
    "NGC1499": {"name": "Nébuleuse Californie", "coords": "60.5000,36.4167"},
    "NGC7293": {"name": "Nébuleuse Hélix", "coords": "337.4104,-20.8373"},
    "M45": {"name": "Pléiades", "coords": "56.8750,24.1167"},
    "M13": {"name": "Amas d'Hercule", "coords": "250.4236,36.4613"},
    "CrabNeb": {"name": "Nébuleuse du Crabe", "coords": "83.6331,22.0145"},
    "SgrA": {"name": "Centre Galaxie (Sgr A*)", "coords": "266.4168,-29.0078"},
}


def _default_station_root() -> str:
    return os.environ.get("ASTROSCAN_STATION_ROOT") or str(Path(__file__).resolve().parent)


def _download_dir(station_root: str) -> str:
    return os.path.join(station_root, "static", "img", "skyview")


def _db_path(station_root: str) -> str:
    return os.path.join(station_root, "data", "archive_stellaire.db")


def fetch_skyview_image(
    target_id: str,
    survey: str = "DSS2 Red",
    size_deg: float = 0.5,
    pixels: int = 512,
    station_root: Optional[str] = None,
) -> dict:
    """
    Télécharge une image NASA SkyView (réseau ou cache data_core/skyview).

    Returns:
        dict avec chemin local et métadonnées (structure historique + champs transparence).
    """
    if target_id not in TARGETS:
        return {"ok": False, "error": f"Cible inconnue: {target_id}"}

    sr = station_root or _default_station_root()
    target = TARGETS[target_id]
    download_dir = _download_dir(sr)
    os.makedirs(download_dir, exist_ok=True)

    safe = get_skyview_safe(
        sr,
        target_id,
        target["coords"],
        survey,
        size_deg,
        pixels,
    )

    if not safe.get("ok") or not safe.get("gif_bytes"):
        return {
            "ok": False,
            "error": str(safe.get("error") or "SkyView indisponible"),
            "fetch_source": safe.get("fetch_source"),
            "stale": safe.get("stale", True),
            "fetched_at_iso": safe.get("fetched_at_iso"),
            "target_id": target_id,
        }

    data = safe["gif_bytes"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"skyview_{target_id}_{survey.replace(' ', '_')}_{ts}.gif"
    dest = os.path.join(download_dir, filename)

    try:
        with open(dest, "wb") as f:
            f.write(data)
    except OSError as e:
        return {
            "ok": False,
            "error": f"Écriture fichier: {e}",
            "fetch_source": safe.get("fetch_source"),
            "stale": safe.get("stale", True),
            "fetched_at_iso": safe.get("fetched_at_iso"),
            "target_id": target_id,
        }

    size_kb = os.path.getsize(dest) // 1024
    logger.info("Image reçue: %s (%sKB)", dest, size_kb)

    _save_to_db(target_id, target, survey, dest, filename, sr)

    return {
        "ok": True,
        "target_id": target_id,
        "target_name": target["name"],
        "survey": survey,
        "survey_desc": SURVEYS.get(survey, survey),
        "filename": filename,
        "path": dest,
        "url_local": f"/static/img/skyview/{filename}",
        "size_kb": size_kb,
        "coords": target["coords"],
        "timestamp": ts,
        "source": "NASA SkyView / HEASARC",
        "fetch_source": safe.get("fetch_source"),
        "stale": safe.get("stale", False),
        "fetched_at_iso": safe.get("fetched_at_iso"),
        "error": safe.get("error"),
    }


def fetch_multiple_surveys(target_id: str, station_root: Optional[str] = None) -> list:
    """Récupère la même cible en 3 surveys différents — vue multi-longueur d'onde."""
    surveys_to_fetch = ["DSS2 Red", "2MASS-K", "GALEX Near UV"]
    results = []
    for s in surveys_to_fetch:
        r = fetch_skyview_image(target_id, survey=s, pixels=400, station_root=station_root)
        results.append(r)
        if r.get("ok"):
            logger.info("✅ %s / %s — %sKB", target_id, s, r.get("size_kb"))
    return results


def _save_to_db(target_id, target, survey, path, filename, station_root: str):
    """Enregistre l'observation SkyView dans la DB."""
    db_path = _db_path(station_root)
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO observations
            (source, titre, analyse_gemini, timestamp, anomalie_score, image_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"NASA_SKYVIEW/{survey}",
                f'{target_id} — {target["name"]}',
                f"Image réelle NASA SkyView. Survey: {survey}. "
                f'Coordonnées: {target["coords"]}. '
                f"Source: NASA Goddard / HEASARC. Aucun compte requis.",
                datetime.now(timezone.utc).isoformat(),
                0.0,
                path,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("DB save: %s", e)


if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║  NASA SKYVIEW — TEST DIRECT              ║")
    print("║  Aucun compte · Aucun token · Gratuit    ║")
    print("╚══════════════════════════════════════════╝\n")

    root = _default_station_root()
    print("Test: M42 — Nébuleuse d'Orion (DSS2 Red)...")
    r = fetch_skyview_image("M42", survey="DSS2 Red", pixels=512, station_root=root)
    if r["ok"]:
        print(f"✅ Image reçue: {r['path']} ({r['size_kb']}KB)")
        print(f"   URL locale: {r['url_local']}")
    else:
        print(f"❌ Erreur: {r['error']}")

    print("\nTest: M31 — Galaxie Andromède (2MASS-K infrarouge)...")
    r2 = fetch_skyview_image("M31", survey="2MASS-K", pixels=512, station_root=root)
    if r2["ok"]:
        print(f"✅ Image reçue: {r2['path']} ({r2['size_kb']}KB)")
    else:
        print(f"❌ Erreur: {r2['error']}")

    print(f"\n📁 Images dans: {_download_dir(root)}")
    print(f"🌌 {len(TARGETS)} cibles disponibles")
    print(f"📡 {len(SURVEYS)} surveys astronomiques")
