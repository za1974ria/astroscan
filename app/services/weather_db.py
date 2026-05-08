"""PASS 22.1 (2026-05-08) — Weather DB helpers.

Extrait depuis station_web.py:205-451 lors de PASS 22.1.

Ce module regroupe les 3 constantes et 8 fonctions liées à la persistance
des bulletins météo (SQLite + JSON sur disque), avec rotation automatique
sur 1 an glissant.

Constantes :
- ``WEATHER_DB_PATH``      : chemin vers ``weather_bulletins.db``
- ``WEATHER_HISTORY_DIR``  : dossier des snapshots quotidiens (history)
- ``WEATHER_ARCHIVE_DIR``  : dossier des snapshots quotidiens (archive)

Fonctions DB :
- ``init_weather_db()`` : création schéma + index + colonnes additionnelles
  (idempotent — utilise CREATE TABLE IF NOT EXISTS et ALTER TABLE
  conditionnels)
- ``save_weather_bulletin(data)`` : insertion d'un bulletin horaire avec
  unicité (date, hour) + cleanup auto >365 jours

Fonctions filesystem :
- ``_init_weather_history_dir`` / ``_cleanup_weather_history_files``
- ``_init_weather_archive_dir`` / ``_cleanup_weather_archive_files``
- ``save_weather_archive_json(data)`` / ``save_weather_history_json(data, score, status)``

Le shim ``station_web`` ré-exporte ces 11 noms (les usages internes du
monolith continuent de fonctionner via la liaison du shim au namespace).

``STATION`` est importé directement depuis ``app.services.station_state``
au lieu de transiter par station_web — pas de cycle au load.

``compute_weather_score``, ``compute_reliability``, ``generate_weather_bulletin``
sont lazy-importés à l'intérieur de ``save_weather_bulletin`` pour rester
cohérent avec la stratégie d'isolation du module.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from app.services.station_state import STATION

# ── Constantes (déplacées depuis station_web.py:205-207) ─────────────
WEATHER_DB_PATH: str = os.path.join(STATION, "weather_bulletins.db")
WEATHER_HISTORY_DIR: str = f'{STATION}/data/weather_history'
WEATHER_ARCHIVE_DIR: str = f'{STATION}/data/weather_archive'


def init_weather_db():
    """Initialise la base locale des bulletins météo (1 an glissant)."""
    try:
        conn = sqlite3.connect(WEATHER_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                hour TEXT,
                temp REAL,
                wind REAL,
                humidity INTEGER,
                pressure REAL,
                wind_direction REAL,
                condition TEXT,
                risk TEXT,
                score INTEGER,
                status TEXT,
                bulletin TEXT,
                source TEXT,
                created_at TEXT,
                UNIQUE(date, hour)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_weather_bulletins_date ON weather_bulletins(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_weather_bulletins_hour ON weather_bulletins(hour)")
        cur.execute("PRAGMA table_info(weather_bulletins)")
        existing_cols = {row[1] for row in cur.fetchall()}
        if "reliability_score" not in existing_cols:
            cur.execute("ALTER TABLE weather_bulletins ADD COLUMN reliability_score INTEGER")
        if "temp_variation" not in existing_cols:
            cur.execute("ALTER TABLE weather_bulletins ADD COLUMN temp_variation REAL")
        if "wind_variation" not in existing_cols:
            cur.execute("ALTER TABLE weather_bulletins ADD COLUMN wind_variation REAL")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WEATHER_DB] init error: {e}")


def _init_weather_history_dir():
    try:
        os.makedirs(WEATHER_HISTORY_DIR, exist_ok=True)
    except Exception as e:
        print(f"[WEATHER_HISTORY] init dir error: {e}")


def _cleanup_weather_history_files():
    try:
        cutoff = datetime.now() - timedelta(days=365)
        for fname in os.listdir(WEATHER_HISTORY_DIR):
            if not fname.endswith(".json"):
                continue
            base = fname[:-5]
            try:
                fdate = datetime.strptime(base, "%Y-%m-%d")
            except Exception:
                continue
            if fdate < cutoff:
                try:
                    os.remove(os.path.join(WEATHER_HISTORY_DIR, fname))
                except Exception:
                    pass
    except Exception as e:
        print(f"[WEATHER_HISTORY] cleanup error: {e}")


def _init_weather_archive_dir():
    try:
        os.makedirs(WEATHER_ARCHIVE_DIR, exist_ok=True)
    except Exception as e:
        print(f"[WEATHER_ARCHIVE] init dir error: {e}")


def _cleanup_weather_archive_files():
    try:
        cutoff = datetime.now() - timedelta(days=365)
        for fname in os.listdir(WEATHER_ARCHIVE_DIR):
            if not fname.endswith(".json"):
                continue
            base = fname[:-5]
            try:
                fdate = datetime.strptime(base, "%Y-%m-%d")
            except Exception:
                continue
            if fdate < cutoff:
                try:
                    os.remove(os.path.join(WEATHER_ARCHIVE_DIR, fname))
                except Exception:
                    pass
    except Exception as e:
        print(f"[WEATHER_ARCHIVE] cleanup error: {e}")


def save_weather_archive_json(data):
    _init_weather_archive_dir()
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(WEATHER_ARCHIVE_DIR, f"{day}.json")
    payload = {
        "date": day,
        "temp": round(float(data.get("temp", 0.0) or 0.0), 1),
        "wind": round(float(data.get("wind", 0.0) or 0.0), 1),
        "humidity": int(data.get("humidity", 0) or 0),
        "pressure": int(round(float(data.get("pressure", 1013) or 1013))),
        "condition": str(data.get("condition") or "Stable"),
        "source": "open-meteo",
        "timestamp": datetime.utcnow().isoformat(),
    }
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WEATHER_ARCHIVE] save error: {e}")
    _cleanup_weather_archive_files()


def save_weather_history_json(data, score, status):
    """Sauvegarde un snapshot météo quotidien en JSON (sans base externe)."""
    _init_weather_history_dir()
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(WEATHER_HISTORY_DIR, f"{day}.json")
    payload = {
        "date": day,
        "temp": round(float(data.get("temp", 0.0)), 1),
        "wind": round(float(data.get("wind", 0.0)), 1),
        "humidity": int(data.get("humidity", 0)),
        "pressure": int(round(float(data.get("pressure", 1015)))),
        "risk": str(data.get("risk") or "FAIBLE"),
        "score": int(score),
        "status": str(status),
    }
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WEATHER_HISTORY] save error: {e}")
    _cleanup_weather_history_files()


def save_weather_bulletin(data):
    # Lazy imports : weather_service helpers consommés uniquement par cette fonction.
    # Évite de payer leur coût au load du module si seules les autres fonctions
    # sont utilisées (init/cleanup dirs, save_*_json).
    from services.weather_service import (
        compute_reliability,
        compute_weather_score,
        generate_weather_bulletin,
    )

    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H")
    conn = sqlite3.connect(WEATHER_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT temp, wind, humidity, pressure
        FROM weather_bulletins
        ORDER BY date DESC, hour DESC
        LIMIT 1
        """
    )
    prev = cur.fetchone()
    previous_row = dict(prev) if prev else None

    score, status = compute_weather_score(data)
    reliability_score = compute_reliability(data, data.get("source"))
    temp_variation = 0.0
    wind_variation = 0.0
    bulletin = generate_weather_bulletin(data, score, status)
    bulletin += (
        f" Indice de fiabilité des données : {reliability_score}%. "
        f"Variation température : ±{temp_variation:.1f}°C. "
        f"Variation vent : ±{wind_variation:.1f} km/h."
    )
    cur.execute(
        "SELECT id FROM weather_bulletins WHERE date = ? AND hour = ? LIMIT 1",
        (day, hour),
    )
    if cur.fetchone():
        conn.close()
        return {
            "saved": False,
            "score": score,
            "status": status,
            "bulletin": bulletin,
            "reliability_score": reliability_score,
            "temp_variation": temp_variation,
            "wind_variation": wind_variation,
        }

    cur.execute(
        """
        INSERT INTO weather_bulletins
        (date, hour, temp, wind, humidity, pressure, wind_direction, condition, risk, score, status, bulletin, source, created_at, reliability_score, temp_variation, wind_variation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            day,
            hour,
            float(data.get("temp")),
            float(data.get("wind")),
            int(data.get("humidity")),
            float(data.get("pressure", 1015)),
            float(data.get("wind_direction", 0.0)),
            str(data.get("condition") or "Unknown"),
            str(data.get("risk") or "FAIBLE"),
            int(score),
            str(status),
            str(bulletin),
            str(data.get("source") or "Open-Meteo"),
            datetime.now(timezone.utc).isoformat(),
            int(reliability_score),
            float(temp_variation),
            float(wind_variation),
        ),
    )
    cur.execute("DELETE FROM weather_bulletins WHERE date < date('now', '-365 days')")
    conn.commit()
    conn.close()
    return {
        "saved": True,
        "score": score,
        "status": status,
        "bulletin": bulletin,
        "reliability_score": reliability_score,
        "temp_variation": temp_variation,
        "wind_variation": wind_variation,
    }


__all__ = [
    "WEATHER_DB_PATH",
    "WEATHER_HISTORY_DIR",
    "WEATHER_ARCHIVE_DIR",
    "init_weather_db",
    "_init_weather_history_dir",
    "_cleanup_weather_history_files",
    "_init_weather_archive_dir",
    "_cleanup_weather_archive_files",
    "save_weather_archive_json",
    "save_weather_history_json",
    "save_weather_bulletin",
]
