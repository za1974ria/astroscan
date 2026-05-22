"""Blueprint APOD — routes /apod, /apod/view, /nasa-apod

Extrait de station_web.py lors de la PHASE 2B / Étape B1 (2026-05-02).

Les 3 routes API (/api/apod, /api/feeds/apod_hd, /api/nasa/apod)
restent dans station_web.py car elles dépendent de helpers internes
(get_cached, _fetch_apod_hd, _fetch_nasa_apod) à extraire séparément
dans une étape ultérieure (B-cache).
"""
import logging
import requests
from flask import Blueprint, Response, abort, jsonify, render_template, request
from app.routes.apod import apod_fr_json_impl, apod_fr_view_impl

apod_bp = Blueprint('apod', __name__)
log = logging.getLogger(__name__)


@apod_bp.route('/apod')
@apod_bp.route('/api/apod')
def apod_fr_json():
    return apod_fr_json_impl(jsonify=jsonify, log=log)


@apod_bp.route('/apod/view')
def apod_fr_view():
    return apod_fr_view_impl(render_template=render_template, log=log)


@apod_bp.route('/nasa-apod')
def page_nasa_apod():
    return render_template('nasa_apod.html')


@apod_bp.route('/api/apod/proxy-image')
def apod_proxy_image():
    """Proxy serveur pour images APOD NASA — contourne CORS / cookies tiers.

    Usage: /api/apod/proxy-image?url=https://apod.nasa.gov/apod/image/...
    Whitelist stricte: apod.nasa.gov uniquement.
    """
    url = (request.args.get('url') or '').strip()
    if not url or not url.startswith('https://apod.nasa.gov/'):
        abort(400, 'Invalid URL')
    try:
        r = requests.get(url, timeout=10, stream=True,
                         headers={'User-Agent': 'AstroScan/1.0'})
        r.raise_for_status()
        return Response(
            r.content,
            mimetype=r.headers.get('Content-Type', 'image/jpeg'),
            headers={
                'Cache-Control': 'public, max-age=86400, immutable',
                'Access-Control-Allow-Origin': '*',
            }
        )
    except Exception as e:
        log.error("APOD proxy error for %s: %s", url, e)
        abort(502, 'Failed to fetch APOD image')
