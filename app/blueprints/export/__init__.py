"""Blueprint Export — CSV/JSON données scientifiques CC BY 4.0.

Routes URL-prefixées (/api/export/*) :
  - visitors.csv / visitors.json
  - observations.json
  - ephemerides.json
  - apod-history.json

Routes globales (sans préfixe) :
  - /api/accuracy/export.csv  (déplacé depuis system_bp lors de PASS 4 phase 2C)
"""
import csv
import io
import json
import sqlite3
from datetime import datetime
from flask import Blueprint, Response, current_app, jsonify

bp = Blueprint("export", __name__, url_prefix="/api/export")
# Sous-blueprint pour les routes export hors-préfixe (globales).
bp_global = Blueprint("export_global", __name__)


def _db():
    return sqlite3.connect(current_app.config["DB_PATH"])


def _meta(description: str, **kwargs) -> dict:
    return {
        "source": "AstroScan-Chohra",
        "url": "https://astroscan.space",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "license": "CC BY 4.0 — Scientific and educational use",
        "description": description,
        **kwargs,
    }


@bp.route("/visitors.csv")
def visitors_csv():
    try:
        conn = _db()
        # PASS 27 — Normalize NL duplicate at query time.
        rows = conn.execute("""
            SELECT
                CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country,
                country_code,
                COUNT(*) as visits,
                DATE(MIN(visited_at)) as first_visit,
                DATE(MAX(visited_at)) as last_visit
            FROM visitor_log
            WHERE country IS NOT NULL AND country != ''
              AND country NOT IN ('Unknown','Inconnu')
              AND (country_code IS NULL OR country_code != 'XX')
              AND is_bot = 0
            GROUP BY
                CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END,
                country_code
            ORDER BY visits DESC
        """).fetchall()
        conn.close()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["country", "country_code", "visits", "first_visit", "last_visit"])
        writer.writerows(rows)
        return Response(
            out.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=astroscan_visitors.csv",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/visitors.json")
def visitors_json():
    try:
        conn = _db()
        # PASS 27 — Normalize NL duplicate at query time.
        rows = conn.execute("""
            SELECT
                CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END AS country,
                country_code,
                COUNT(*) as visits,
                DATE(MIN(visited_at)) as first_visit,
                DATE(MAX(visited_at)) as last_visit
            FROM visitor_log
            WHERE country IS NOT NULL AND country != ''
              AND country NOT IN ('Unknown','Inconnu')
              AND (country_code IS NULL OR country_code != 'XX')
              AND is_bot = 0
            GROUP BY
                CASE WHEN country_code = 'NL' THEN 'Netherlands' ELSE country END,
                country_code
            ORDER BY visits DESC
        """).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM visitor_log WHERE is_bot=0"
        ).fetchone()[0]
        conn.close()
        data = {
            "metadata": _meta(
                "Global visitor statistics by country",
                count=len(rows),
                total_visits=total,
            ),
            "data": [
                {
                    "country": r[0], "country_code": r[1], "visits": r[2],
                    "first_visit": r[3], "last_visit": r[4],
                }
                for r in rows
            ],
        }
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/observations.json")
def observations_json():
    try:
        conn = _db()
        rows = conn.execute("""
            SELECT id, timestamp, source, objets_detectes,
                   anomalie, score_confiance, analyse_gemini
            FROM observations
            ORDER BY timestamp DESC LIMIT 500
        """).fetchall()
        conn.close()
        data = {
            "metadata": _meta(
                "Astronomical observations with AI analysis (Claude/Gemini)",
                count=len(rows),
            ),
            "data": [
                {
                    "id": r[0], "timestamp": r[1], "source": r[2],
                    "objects_detected": r[3], "anomaly": r[4],
                    "confidence_score": r[5], "ai_analysis": r[6],
                }
                for r in rows
            ],
        }
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/ephemerides.json")
def ephemerides_json():
    """Export JSON éphémérides Tlemcen avec métadonnées scientifiques."""
    try:
        from services.cache_service import cache_get
        cached = cache_get('eph_tlemcen', 300) or {}
        export = {
            "metadata": {
                "source": "AstroScan-Chohra",
                "location": "Tlemcen, Algeria",
                "coordinates": {"lat": 34.8753, "lon": 1.3167, "alt_m": 800},
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "license": "CC BY 4.0 — Scientific use",
                "url": "https://astroscan.space/api/export/ephemerides.json",
                "computation": "astropy 7.2 + SGP4",
            }
        }
        export.update(cached)
        return Response(
            json.dumps(export, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/apod-history.json")
def apod_history_json():
    """Export JSON historique APOD depuis le cache local."""
    try:
        from station_web import STATION
        cache_path = f"{STATION}/data/apod_cache.json"
        with open(cache_path) as f:
            apod_cache = json.load(f)
        data = {
            "metadata": _meta(
                "NASA APOD local cache — AstroScan FR translations CC BY 4.0",
                count=len(apod_cache),
            ),
            "data": apod_cache,
        }
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Routes export hors-préfixe (déplacées depuis system_bp PASS 4 2C) ──────

@bp_global.route('/api/accuracy/export.csv')
def api_accuracy_export_csv():
    """Export CSV historique de précision ISS."""
    from app.services.accuracy_history import get_accuracy_history
    rows = get_accuracy_history()
    lines = ["ts,distance_km"]
    for row in rows:
        ts = row.get("ts", "")
        distance = row.get("distance_km", "")
        lines.append(f"{ts},{distance}")
    csv_payload = "\n".join(lines) + "\n"
    return Response(
        csv_payload,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="accuracy_history.csv"'},
    )
