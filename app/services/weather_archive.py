"""Weather archive helpers — DB bulletins + JSON history/archive.

Extrait de station_web.py (PASS 7) pour permettre l'utilisation
par weather_bp sans dépendance circulaire.

Tables utilisées :
    weather_bulletins (SQLite, 1 an glissant) — bulletins horaires.
Fichiers JSON :
    {STATION}/data/weather_history/YYYY-MM-DD.json — snapshot quotidien.
    {STATION}/data/weather_archive/YYYY-MM-DD.json — archive Open-Meteo.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.config import (
    WEATHER_DB_PATH, WEATHER_HISTORY_DIR, WEATHER_ARCHIVE_DIR,
)

log = logging.getLogger(__name__)


def init_weather_db() -> None:
    """Initialise la base locale des bulletins météo (1 an glissant)."""
    try:
        conn = sqlite3.connect(WEATHER_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, hour TEXT,
                temp REAL, wind REAL, humidity INTEGER, pressure REAL,
                wind_direction REAL, condition TEXT, risk TEXT,
                score INTEGER, status TEXT, bulletin TEXT,
                source TEXT, created_at TEXT,
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
        log.warning("[WEATHER_DB] init error: %s", e)


def _init_weather_history_dir() -> None:
    try:
        os.makedirs(WEATHER_HISTORY_DIR, exist_ok=True)
    except Exception as e:
        log.warning("[WEATHER_HISTORY] init dir error: %s", e)


def _cleanup_weather_history_files() -> None:
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
        log.warning("[WEATHER_HISTORY] cleanup error: %s", e)


def _init_weather_archive_dir() -> None:
    try:
        os.makedirs(WEATHER_ARCHIVE_DIR, exist_ok=True)
    except Exception as e:
        log.warning("[WEATHER_ARCHIVE] init dir error: %s", e)


def _cleanup_weather_archive_files() -> None:
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
        log.warning("[WEATHER_ARCHIVE] cleanup error: %s", e)


def save_weather_archive_json(data: Dict[str, Any]) -> None:
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
        log.warning("[WEATHER_ARCHIVE] save error: %s", e)
    _cleanup_weather_archive_files()


def save_weather_history_json(data: Dict[str, Any], score: int, status: str) -> None:
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
        log.warning("[WEATHER_HISTORY] save error: %s", e)
    _cleanup_weather_history_files()


def save_weather_bulletin(data: Dict[str, Any]) -> Dict[str, Any]:
    """Insère un bulletin horaire dans weather_bulletins (idempotent par (date, hour))."""
    from services.weather_service import (
        compute_weather_score, compute_reliability, generate_weather_bulletin,
    )

    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H")
    conn = sqlite3.connect(WEATHER_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

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
        (date, hour, temp, wind, humidity, pressure, wind_direction, condition,
         risk, score, status, bulletin, source, created_at,
         reliability_score, temp_variation, wind_variation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            day, hour,
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
