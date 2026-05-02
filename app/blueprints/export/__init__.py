"""Blueprint Export — CSV/JSON données scientifiques CC BY 4.0."""
import csv
import io
import json
import sqlite3
from datetime import datetime
from flask import Blueprint, Response, current_app, jsonify

bp = Blueprint("export", __name__, url_prefix="/api/export")


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
        rows = conn.execute("""
            SELECT country, country_code,
                   COUNT(*) as visits,
                   DATE(MIN(visited_at)) as first_visit,
                   DATE(MAX(visited_at)) as last_visit
            FROM visitor_log
            WHERE country IS NOT NULL AND country != ''
              AND country NOT IN ('Unknown','Inconnu')
              AND (country_code IS NULL OR country_code != 'XX')
              AND is_bot = 0
            GROUP BY country, country_code
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
        rows = conn.execute("""
            SELECT country, country_code,
                   COUNT(*) as visits,
                   DATE(MIN(visited_at)) as first_visit,
                   DATE(MAX(visited_at)) as last_visit
            FROM visitor_log
            WHERE country IS NOT NULL AND country != ''
              AND country NOT IN ('Unknown','Inconnu')
              AND (country_code IS NULL OR country_code != 'XX')
              AND is_bot = 0
            GROUP BY country, country_code
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
