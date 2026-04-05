#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collecte des flux télescopes → archive_stellaire.db
Sources : HUBBLE/ESA, CHANDRA/NASA, MAST/JWST, NASA_APOD (7 derniers jours)
Lancer : python3 telescope_feeds.py
Cron : 0 */6 * * * cd /root/astro_scan && python3 telescope_feeds.py >> logs/telescope_feeds.log 2>&1
"""

import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATION = Path(__file__).resolve().parent
DB_PATH = STATION / "data" / "archive_stellaire.db"
ENV_FILE = STATION / ".env"

def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def curl_get(url, timeout=20):
    try:
        r = subprocess.run(
            ["curl", "-s", "-L", "--max-time", str(timeout),
             "-H", "User-Agent: ORBITAL-CHOHRA/1.0", url],
            capture_output=True, text=True, timeout=timeout + 5, cwd=str(STATION)
        )
        return r.stdout
    except Exception as e:
        print(f"curl error {url[:50]}: {e}", file=sys.stderr)
        return None

def db_insert(conn, source, title, analyse_gemini, objets_detectes="", score_confiance=0.85):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """INSERT INTO observations (timestamp, source, title, analyse_gemini, objets_detectes, anomalie, score_confiance)
           VALUES (?, ?, ?, ?, ?, 0, ?)""",
        (ts, source, title or "", analyse_gemini or "", objets_detectes or "", score_confiance)
    )

def exists_by_source_title(conn, source, title):
    if not title:
        return False
    row = conn.execute(
        "SELECT 1 FROM observations WHERE source = ? AND title = ? LIMIT 1",
        (source, title)
    ).fetchone()
    return row is not None

def fetch_nasa_apod(conn, api_key):
    """7 derniers jours APOD."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    url = f"https://api.nasa.gov/planetary/apod?api_key={api_key}&start_date={start_str}&end_date={end_str}"
    raw = curl_get(url)
    if not raw:
        return 0
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            data = [data] if isinstance(data, dict) and data.get("date") else []
        n = 0
        for item in data:
            title = item.get("title") or item.get("date") or ""
            if exists_by_source_title(conn, "NASA_APOD", title):
                continue
            expl = (item.get("explanation") or "")[:1500]
            media = item.get("media_type", "image")
            obj = "image" if media == "image" else "video"
            db_insert(conn, "NASA_APOD", title, expl, obj, 0.9)
            n += 1
        return n
    except Exception as e:
        print(f"APOD parse error: {e}", file=sys.stderr)
        return 0

def fetch_hubble_esa(conn):
    """Hubble Space Telescope — observations ESA (curated)."""
    entries = [
        ("Pillars of Creation (M16)", "Nébuleuse M16 — piliers de gaz et poussière. Hubble Space Telescope. ESA/NASA.", "nebula"),
        ("Galaxy M51 Whirlpool", "Galaxie du Tourbillon M51. Hubble. ESA/NASA.", "galaxy"),
        ("Carina Nebula", "Nébuleuse de la Carène. Région de formation stellaire. Hubble ESA.", "nebula"),
        ("Andromeda M31", "Galaxie d'Andromède M31. Hubble. ESA/NASA.", "galaxy"),
        ("Crab Nebula M1", "Nébuleuse du Crabe — reste de supernova. Hubble ESA.", "nebula"),
        ("Jupiter Great Red Spot", "Jupiter — Grande Tache Rouge. Hubble ESA.", "planet"),
    ]
    n = 0
    for title, analyse, obj in entries:
        if exists_by_source_title(conn, "HUBBLE/ESA", title):
            continue
        db_insert(conn, "HUBBLE/ESA", title, analyse, obj, 0.88)
        n += 1
    return n

def fetch_chandra_nasa(conn):
    """Chandra X-Ray — M87, Cas A, Perseus, Sgr A* (curated)."""
    entries = [
        ("M87 Black Hole", "Galaxie M87 — trou noir supermassif. Chandra X-Ray Observatory. NASA.", "galaxy"),
        ("Cassiopeia A", "Cassiopeia A — reste de supernova. Chandra NASA.", "supernova"),
        ("Perseus Cluster", "Amas de Persée — gaz chaud en X. Chandra NASA.", "cluster"),
        ("Sagittarius A*", "Sagittarius A* — centre galactique. Chandra X-Ray. NASA.", "galaxy"),
    ]
    n = 0
    for title, analyse, obj in entries:
        if exists_by_source_title(conn, "CHANDRA/NASA", title):
            continue
        db_insert(conn, "CHANDRA/NASA", title, analyse, obj, 0.87)
        n += 1
    return n

def fetch_mast_jwst(conn):
    """James Webb / MAST — Pilliers, SMACS, Carina, exoplanètes (curated)."""
    entries = [
        ("Pillars of Creation (JWST)", "Piliers de la Création — James Webb Space Telescope. NASA/ESA/CSA.", "nebula"),
        ("SMACS 0723", "SMACS 0723 — champ profond JWST. Galaxies lointaines.", "galaxy"),
        ("Carina Nebula (JWST)", "Nébuleuse Carina — JWST. Formation stellaire.", "nebula"),
        ("Exoplanet WASP-96 b", "Exoplanète WASP-96 b — spectre atmosphérique. JWST.", "planet"),
        ("Stephan's Quintet", "Quintette de Stephan — JWST. Groupe de galaxies.", "galaxy"),
    ]
    n = 0
    for title, analyse, obj in entries:
        if exists_by_source_title(conn, "MAST/JWST", title):
            continue
        db_insert(conn, "MAST/JWST", title, analyse, obj, 0.88)
        n += 1
    return n

def main():
    load_env()
    STATION.mkdir(parents=True, exist_ok=True)
    (STATION / "logs").mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        print("DB not found:", DB_PATH, file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        n_apod = fetch_nasa_apod(conn, os.environ.get("NASA_API_KEY", "DEMO_KEY"))
        n_hubble = fetch_hubble_esa(conn)
        n_chandra = fetch_chandra_nasa(conn)
        n_jwst = fetch_mast_jwst(conn)
        conn.commit()
        print(f"telescope_feeds: APOD={n_apod} Hubble={n_hubble} Chandra={n_chandra} JWST={n_jwst}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
