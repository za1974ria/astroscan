"""Blueprint ISS — routes simples sans TLE_CACHE

Extrait de station_web.py lors de la PHASE 2B / Étape B3b (2026-05-02).

SCOPE B3b (5 routes) :
- /iss-tracker  : render_template
- /orbital      : render_template
- /orbital-map  : render_template + CESIUM_TOKEN
- /api/tle/sample, /api/tle/catalog : JSON hardcodés

Les autres routes ISS/TLE restent dans station_web.py jusqu'à
B3b-bis (lazy imports), B3c (TLE_CACHE accesseur), B-cache (services/cache_service),
et B-state (refonte fetch_tle_from_celestrak global TLE_CACHE).
"""
import os
import logging
from flask import Blueprint, jsonify, render_template

iss_bp = Blueprint('iss', __name__)
log = logging.getLogger(__name__)

# CESIUM_TOKEN — recalculé à l'appel pour cohérence avec station_web.py L.458
def _cesium_token():
    return os.getenv("CESIUM_TOKEN", "")


@iss_bp.route('/iss-tracker')
def iss_tracker_page():
    return render_template('iss_tracker.html')


@iss_bp.route('/orbital')
def orbital_dashboard():
    return render_template('orbital_dashboard.html')


@iss_bp.route('/orbital-map')
def orbital_map_page():
    return render_template('orbital_map.html', cesium_token=_cesium_token())


@iss_bp.route("/api/tle/sample")
def tle_sample():
    satellites = [
        {
            "name": "Hubble",
            "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993",
            "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"
        },
        {
            "name": "NOAA 19",
            "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996",
            "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"
        }
    ]
    return jsonify({"satellites": satellites})


@iss_bp.route("/api/tle/catalog")
def tle_catalog():
    """Catalog of satellites with TLE data; frontend may limit display count."""
    satellites = [
        {
            "name": "Hubble",
            "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993",
            "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"
        },
        {
            "name": "NOAA 19",
            "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996",
            "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"
        }
    ]
    return jsonify({"satellites": satellites})
