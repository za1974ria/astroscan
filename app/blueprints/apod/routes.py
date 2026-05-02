"""Blueprint APOD — routes /apod, /apod/view, /nasa-apod

Extrait de station_web.py lors de la PHASE 2B / Étape B1 (2026-05-02).

Les 3 routes API (/api/apod, /api/feeds/apod_hd, /api/nasa/apod)
restent dans station_web.py car elles dépendent de helpers internes
(get_cached, _fetch_apod_hd, _fetch_nasa_apod) à extraire séparément
dans une étape ultérieure (B-cache).
"""
import logging
from flask import Blueprint, jsonify, render_template
from app.routes.apod import apod_fr_json_impl, apod_fr_view_impl

apod_bp = Blueprint('apod', __name__)
log = logging.getLogger(__name__)


@apod_bp.route('/apod')
def apod_fr_json():
    return apod_fr_json_impl(jsonify=jsonify, log=log)


@apod_bp.route('/apod/view')
def apod_fr_view():
    return apod_fr_view_impl(render_template=render_template, log=log)


@apod_bp.route('/nasa-apod')
def page_nasa_apod():
    return render_template('nasa_apod.html')
