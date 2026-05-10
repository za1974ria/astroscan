"""PASS 20.4 (2026-05-08) — Telescope helpers.

Extrait depuis station_web.py (L2833-2929) lors de PASS 20.4.

Ce module contient le pipeline nocturne de capture FITS Harvard
MicroObservatory pour Tlemcen, utilisé par telescope_bp via lazy import
``from station_web import _telescope_nightly_tlemcen``.

Les helpers ``_mo_fetch_catalog_today``, ``_mo_visible_tonight``,
``_mo_fits_to_jpg`` restent dans station_web (hors périmètre PASS 20.4)
et sont importés en lazy à l'intérieur de la fonction pour éviter le
cycle station_web ↔ telescope_helpers au load.
"""
from __future__ import annotations

from app.constants.observatory import (
    OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M, OBSERVER_CITY,
)

import os

from app.services.station_state import STATION


def _telescope_nightly_tlemcen():
    """
    Pipeline nocturne complet :
    1. Scan répertoire Harvard MicroObservatory
    2. Sélection 3 objets visibles depuis Tlemcen (altitude > 20° à 23h00 UTC)
    3. Téléchargement FITS + conversion JPG
    4. Sauvegarde métadonnées nightly_meta.json
    """
    import json
    import re
    import urllib.request
    from datetime import datetime, timezone

    # Lazy imports pour éviter le cycle station_web ↔ telescope_helpers au load.
    from station_web import (
        _mo_fetch_catalog_today,
        _mo_fits_to_jpg,
        _mo_visible_tonight,
        cache_set,
        log,
    )

    log.info('telescope_nightly: démarrage pipeline — Tlemcen 34.87°N 1.32°W')

    try:
        mo_catalog = _mo_fetch_catalog_today()
    except Exception as e:
        log.error('telescope_nightly: catalog error: %s', e)
        mo_catalog = {}

    try:
        visible = _mo_visible_tonight()
        log.info('telescope_nightly: %d objets visibles', len(visible))
    except Exception as e:
        log.error('telescope_nightly: visibility error: %s', e)
        visible = []

    results = []
    used_labels = set()

    for obj in visible:
        if len(results) >= 3:
            break
        label = obj['label']
        if label in used_labels:
            continue

        entries = mo_catalog.get(obj['prefix'], [])
        if not entries:
            log.debug('telescope_nightly: %s — aucun FITS MO disponible', obj['prefix'])
            continue

        entry = entries[0]  # Le plus récent
        fits_url = entry['url']
        captured_at = entry['captured_at']

        try:
            req = urllib.request.Request(fits_url, headers={'User-Agent': 'AstroScan-Chohra/2.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                fits_bytes = r.read()
            if len(fits_bytes) < 2880:  # FITS minimum = 1 bloc de 2880 octets
                log.warning('telescope_nightly: %s FITS trop petit (%d o)', obj['prefix'], len(fits_bytes))
                continue

            safe_stem = re.sub(r'[^\w]', '_', os.path.splitext(entry['filename'])[0])
            jpg_name  = f"nightly_{safe_stem}.jpg"
            jpg_path  = os.path.join(STATION, 'telescope_live', jpg_name)

            hdr_date = _mo_fits_to_jpg(fits_bytes, jpg_path)

            results.append({
                'object_label':       obj['label'],
                'object_type':        obj['type'],
                'object_prefix':      obj['prefix'],
                'altitude_deg':       obj['alt'],
                'filename_fits':      entry['filename'],
                'jpg':                jpg_name,
                'fits_url':           fits_url,
                'captured_at_utc':    captured_at.isoformat(),
                'captured_at_display': captured_at.strftime('%d/%m/%Y %H:%M UTC'),
                'obs_date_header':    hdr_date or '',
                'source':             'Harvard MicroObservatory · CfA · Cambridge MA',
                'telescope_aperture': '6 pouces (152 mm)',
                'fetched_at':         datetime.now(timezone.utc).isoformat(),
            })
            used_labels.add(label)
            log.info('telescope_nightly: ✓ %s — alt=%.1f° — capturé %s',
                     obj['label'], obj['alt'], captured_at.strftime('%d/%m/%Y %H:%M UTC'))

        except Exception as e:
            log.warning('telescope_nightly: %s → skipped: %s', obj['prefix'], e)

    meta = {
        'run_at':       datetime.now(timezone.utc).isoformat(),
        'run_date':     datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'location':     {'city': 'Tlemcen', 'lat': OBSERVER_LAT, 'lon': OBSERVER_LON, 'alt_m': OBSERVER_ALT_M},
        'source':       'Harvard MicroObservatory — waps.cfa.harvard.edu',
        'note':         'FITS originaux · Télescopes robotiques CCD 6" · Pipeline automatique AstroScan',
        'total_visible_tonight': len(visible),
        'images':       results,
    }
    meta_path = os.path.join(STATION, 'telescope_live', 'nightly_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)

    cache_set('mo_catalog_today', None)
    log.info('telescope_nightly: terminé — %d image(s) collectée(s)', len(results))
    return meta


__all__ = ["_telescope_nightly_tlemcen"]
