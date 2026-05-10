"""MicroObservatory helpers — Harvard Smithsonian image directory scrape + FITS preview.

Extrait de station_web.py (PASS 15) pour permettre l'utilisation
par cameras_bp sans dépendance circulaire.

PASS 27.9 (2026-05-09) — Ajout de 4 helpers `_mo_*` (déplacés verbatim
depuis station_web.py L1359-1485) + 3 constantes catalogue (_MO_DIR_URL,
_MO_DL_BASE, _MO_OBJECT_CATALOG, 40 préfixes objets). Le module devient
la source de vérité unique des helpers MO. telescope_helpers.py:35
continue de les consommer via le re-export du shim station_web.

Sources :
    https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/
    https://mo-www.cfa.harvard.edu/ImageDirectory/<filename>

Fonctions exposées :
    fetch_microobservatory_images() -> dict      # scrape page index (PASS 15)
    _mo_parse_filename(name) -> dict|None        # parse 'ObjectYYMMDDHHMMSS.FITS'
    _mo_fetch_catalog_today() -> dict            # catalogue {prefix → entries} 30j, cache 1h
    _mo_visible_tonight() -> list                # objets MO visibles depuis Tlemcen 23h UTC
    _mo_fits_to_jpg(fits_bytes, save_path) -> str  # convertit FITS→JPG (ZScale + colormap hot)
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

from app.services.http_client import _curl_get
from services.cache_service import cache_get, cache_set
from app.constants.observatory import OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M

log = logging.getLogger(__name__)


def fetch_microobservatory_images():
    """
    Scrape recent images from Harvard MicroObservatory image directory.
    Keeps only entries that look recent (<= 10 days) when a date can be inferred.
    """
    base = "https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/"
    page_url = base + "ImageDirectory.php"
    now = datetime.now(timezone.utc)
    out = []
    try:
        html = _curl_get(page_url, timeout=20) or ""
        if not html:
            return {"ok": False, "images": [], "source": page_url, "error": "empty response"}

        def _format_object_name_from_filename(name):
            stem = (name or "").rsplit(".", 1)[0]
            # Extract object segment before first YYMMDD pattern.
            mdt = re.search(r"\d{6}", stem)
            obj_raw = stem[:mdt.start()] if mdt else stem
            obj_raw = obj_raw.replace("_", " ").replace("-", " ").strip()

            # Split CamelCase chunks.
            obj_raw = re.sub(r"([a-z])([A-Z])", r"\1 \2", obj_raw)

            # Normalize requested NGC/M patterns.
            # Example: NGC5457M101 -> NGC 5457 / M101
            m_nm = re.match(r"^\s*NGC\s*(\d+)\s*M\s*(\d+)\s*$", obj_raw, flags=re.I)
            if m_nm:
                obj_raw = f"NGC {m_nm.group(1)} / M{m_nm.group(2)}"
            else:
                obj_raw = re.sub(r"\bNGC(\d+)\b", r"NGC \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bIC(\d+)\b", r"IC \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bM(\d+)\b", r"M\1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bHD(\d+)\b", r"HD \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bHIP(\d+)\b", r"HIP \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\bSAO(\d+)\b", r"SAO \1", obj_raw, flags=re.I)
            obj_raw = re.sub(r"\s+", " ", obj_raw).strip()

            # Specific normalization requested.
            obj_raw = obj_raw.replace("T Coronae Bore", "T Coronae Borealis")
            if obj_raw.lower() == "t coronae bore":
                obj_raw = "T Coronae Borealis"
            return obj_raw or "Unknown object"

        def _parse_date_obs_from_filename(name):
            stem = (name or "").rsplit(".", 1)[0]
            # YYMMDDHHMMSS
            m = re.search(r"(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", stem)
            if not m:
                return None
            yy, mo, dd, hh, mi, ss = m.groups()
            try:
                if not (1 <= int(mo) <= 12 and 1 <= int(dd) <= 31 and 0 <= int(hh) <= 23 and 0 <= int(mi) <= 59 and 0 <= int(ss) <= 59):
                    return None
            except Exception:
                return None
            return f"{yy}/{mo}/{dd} {hh}:{mi}:{ss} UTC"

        # Extract candidate image URLs from href/src.
        # Keep only FITS/FIT/JPG families (requested).
        link_re = re.compile(r'''(?:href|src)=["']([^"']+\.(?:fits|fit|jpg|jpeg))["']''', re.I)
        candidates = link_re.findall(html)

        # Also try generic absolute URLs in text.
        abs_re = re.compile(r'''https?://[^\s"'<>]+\.(?:fits|fit|jpg|jpeg)''', re.I)
        candidates.extend(abs_re.findall(html))

        seen = set()
        for raw in candidates:
            url = raw.strip()
            if not url:
                continue
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = base.rstrip("/") + url
            elif not url.lower().startswith("http"):
                url = base + url
            if url in seen:
                continue
            seen.add(url)

            name = url.split("/")[-1] or "image"
            lname = name.lower()

            # Exclusion criteria for UI/non-astronomical assets.
            excluded_tokens = ["icon", "logo", "crop", "observatory2300", "fits_icon"]
            if any(tok in lname for tok in excluded_tokens):
                continue

            # Keep only requested extensions explicitly.
            if not (lname.endswith(".fits") or lname.endswith(".fit") or lname.endswith(".jpg") or lname.endswith(".jpeg")):
                continue

            # Keep only names likely tied to astronomical objects.
            # Accept common catalogs/designators (M, NGC, IC, HD, HIP, SAO, Messier, Nebula, Galaxy, etc.).
            astro_name_re = re.compile(
                r'(?:^|[_\-\s])('
                r'm\d{1,3}|ngc\d{1,4}|ic\d{1,4}|hd\d{1,6}|hip\d{1,6}|sao\d{1,6}|'
                r'iss|j\d{4,}|'
                r'andromeda|orion|nebula|galaxy|cluster|pleiades|vega|sirius|'
                r'jupiter|saturn|mars|moon|luna|sun|solar|comet|asteroid'
                r')',
                re.I
            )
            if not astro_name_re.search(lname):
                continue

            # Try to infer date from URL patterns: YYYYMMDD or YYYY-MM-DD.
            date_obj = None
            m1 = re.search(r"(20\d{2})(\d{2})(\d{2})", url)
            m2 = re.search(r"(20\d{2})-(\d{2})-(\d{2})", url)
            try:
                if m2:
                    y, mo, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
                    date_obj = datetime(y, mo, d, tzinfo=timezone.utc)
                elif m1:
                    y, mo, d = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
                    date_obj = datetime(y, mo, d, tzinfo=timezone.utc)
            except Exception:
                date_obj = None

            # Keep only <=10 days if date is known.
            if date_obj is not None:
                age_days = (now - date_obj).days
                if age_days < 0 or age_days > 10:
                    continue

            obj = _format_object_name_from_filename(name)
            date_obs = _parse_date_obs_from_filename(name)
            out.append({
                "nom": name,
                "url": url,
                "objet": obj,
                "date": date_obj.isoformat().replace("+00:00", "Z") if date_obj else None,
                "date_obs": date_obs,
            })

        # Sort by date desc when available; unknown dates last.
        out.sort(key=lambda x: (x["date"] is None, x["date"] or ""), reverse=False)
        out = out[:30]
        return {"ok": True, "images": out, "source": page_url, "count": len(out)}
    except Exception as e:
        log.warning("microobservatory/images scrape: %s", e)
        return {"ok": False, "images": [], "source": page_url, "error": str(e)}

# Compat alias
_fetch_microobservatory_images = fetch_microobservatory_images


# ══════════════════════════════════════════════════════════════════════════════
# PASS 27.9 — PIPELINE NOCTURNE TLEMCEN
# Sélection 3 objets MO visibles ce soir, téléchargement FITS Harvard,
# conversion JPG avec métadonnées de capture.
# Déplacé verbatim depuis station_web.py L1307-1485.
# ══════════════════════════════════════════════════════════════════════════════

_MO_DIR_URL  = "https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/ImageDirectory.php"
_MO_DL_BASE  = "https://mo-www.cfa.harvard.edu/ImageDirectory/"   # URL réelle de téléchargement FITS

# Correspondance préfixes MO → coordonnées + labels FR
_MO_OBJECT_CATALOG = {
    'Moon':         {'ra': None,   'dec': None,   'type': 'Satellite nat.', 'label': 'Lune',                 'body': 'moon'},
    'Jupiter':      {'ra': None,   'dec': None,   'type': 'Planète',        'label': 'Jupiter',              'body': 'jupiter'},
    'Pluto':        {'ra': None,   'dec': None,   'type': 'Planète naine',  'label': 'Pluton',               'body': 'pluto'},
    'AndromedaGal': {'ra': 10.68,  'dec': 41.27,  'type': 'Galaxie',        'label': 'M31 — Andromède'},
    'OrionNebula':  {'ra': 83.82,  'dec': -5.39,  'type': 'Nébuleuse',      'label': 'M42 — Orion'},
    'OrionNebulaM': {'ra': 83.82,  'dec': -5.39,  'type': 'Nébuleuse',      'label': 'M42 — Orion'},
    'Pleiades':     {'ra': 56.87,  'dec': 24.12,  'type': 'Amas ouvert',    'label': 'M45 — Pléiades'},
    'HerculesClus': {'ra': 250.42, 'dec': 36.46,  'type': 'Amas glob.',     'label': 'M13 — Hercule'},
    'RingNebulaM5': {'ra': 283.40, 'dec': 33.03,  'type': 'Nébuleuse plan.','label': 'M57 — Lyre'},
    'DumbbellNebu': {'ra': 299.90, 'dec': 22.72,  'type': 'Nébuleuse plan.','label': 'M27 — Haltère'},
    'M-81SpiralGa': {'ra': 148.89, 'dec': 69.07,  'type': 'Galaxie',        'label': 'M81 — Bode'},
    'NGC3031M81':   {'ra': 148.89, 'dec': 69.07,  'type': 'Galaxie',        'label': 'M81 — Bode'},
    'M-51Whirlpoo': {'ra': 202.47, 'dec': 47.20,  'type': 'Galaxie',        'label': 'M51 — Tourbillon'},
    'CrabNebulaM1': {'ra': 83.63,  'dec': 22.01,  'type': 'Reste supernova','label': 'M1 — Crabe'},
    'M-101SpiralG': {'ra': 210.80, 'dec': 54.35,  'type': 'Galaxie',        'label': 'M101 — Épinglier'},
    'NGC5457M101':  {'ra': 210.80, 'dec': 54.35,  'type': 'Galaxie',        'label': 'NGC5457/M101'},
    'LagoonNebula': {'ra': 270.92, 'dec': -24.38, 'type': 'Nébuleuse',      'label': 'M8 — Lagune'},
    'EagleNebulaM': {'ra': 274.70, 'dec': -13.79, 'type': 'Nébuleuse',      'label': 'M16 — Aigle'},
    'RosetteNebul': {'ra': 97.65,  'dec': 4.93,   'type': 'Nébuleuse',      'label': 'Nébuleuse de la Rosette'},
    'Quasar3C273':  {'ra': 187.28, 'dec': 2.05,   'type': 'Quasar',         'label': 'Quasar 3C 273'},
    'M87':          {'ra': 187.71, 'dec': 12.39,  'type': 'Galaxie géante', 'label': 'M87 — Virgo'},
    'SombreroGala': {'ra': 190.00, 'dec': -11.62, 'type': 'Galaxie',        'label': 'M104 — Sombrero'},
    'SagittariusA': {'ra': 266.42, 'dec': -29.01, 'type': 'Noyau galactique','label': 'Sgr A* — Centre galactique'},
    'MilkyWay':     {'ra': 266.42, 'dec': -29.01, 'type': 'Voie Lactée',   'label': 'Voie Lactée — Cœur galactique'},
    'OpenClusterM': {'ra': 92.27,  'dec': 24.33,  'type': 'Amas ouvert',   'label': 'Amas ouvert — Gémeaux'},
    'NGC891':       {'ra': 35.64,  'dec': 42.35,  'type': 'Galaxie',        'label': 'NGC 891'},
    'CentaurusA':   {'ra': 201.36, 'dec': -43.02, 'type': 'Galaxie radio',  'label': 'Cen A / NGC 5128'},
    'Messier15':    {'ra': 322.49, 'dec': 12.17,  'type': 'Amas glob.',     'label': 'M15 — Pégase'},
    'BetaLyr':      {'ra': 282.52, 'dec': 33.36,  'type': 'Étoile double',  'label': 'Beta Lyrae'},
    'CygnusX-1':    {'ra': 299.59, 'dec': 35.20,  'type': 'Trou noir binaire','label': 'Cygnus X-1'},
    'Algol':        {'ra': 47.04,  'dec': 40.96,  'type': 'Étoile variable','label': 'Algol (β Persei)'},
    'DeltaCephei':  {'ra': 337.29, 'dec': 58.42,  'type': 'Céphéide',       'label': 'Delta Cephei'},
    'M-82Irregula': {'ra': 148.97, 'dec': 69.68,  'type': 'Galaxie irr.',   'label': 'M82 — Cigare'},
    'M82Irregular': {'ra': 148.97, 'dec': 69.68,  'type': 'Galaxie irr.',   'label': 'M82 — Cigare'},
    'NGC4579M58':   {'ra': 189.43, 'dec': 11.82,  'type': 'Galaxie',        'label': 'M58 — Virgo'},
    'NGC3351M95':   {'ra': 160.99, 'dec': 11.70,  'type': 'Galaxie',        'label': 'M95 — Leo'},
    'BeehiveClust': {'ra': 130.10, 'dec': 19.67,  'type': 'Amas ouvert',   'label': 'M44 — La Ruche'},
}


def _mo_parse_filename(name):
    """Parse 'ObjectName260422221047.FITS' → dict avec prefix, captured_at, url."""
    stem = os.path.splitext(name)[0]
    m = re.search(r'^(.+?)(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$', stem)
    if not m:
        return None
    prefix = m.group(1)
    yy, mo, dd, hh, mi, ss = m.groups()[1:]
    try:
        dt = datetime(2000 + int(yy), int(mo), int(dd), int(hh), int(mi), int(ss), tzinfo=timezone.utc)
    except ValueError:
        return None
    return {'prefix': prefix, 'filename': name, 'captured_at': dt, 'url': _MO_DL_BASE + name}


def _mo_fetch_catalog_today():
    """
    Lit le répertoire MicroObservatory et retourne {prefix → [entries]}
    pour les 30 derniers jours. Cache 1h.
    """
    from datetime import timedelta

    cached = cache_get('mo_catalog_today', 3600)
    if cached is not None:
        return cached

    html = _curl_get(_MO_DIR_URL, timeout=25) or ""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    catalog = {}
    for name in re.findall(r'\b([\w\-]+\d{12}\.FITS)\b', html, re.I):
        parsed = _mo_parse_filename(name)
        if not parsed or parsed['captured_at'] < cutoff:
            continue
        prefix = parsed['prefix']
        if prefix not in catalog:
            catalog[prefix] = []
        catalog[prefix].append(parsed)

    for k in catalog:
        catalog[k].sort(key=lambda x: x['captured_at'], reverse=True)

    cache_set('mo_catalog_today', catalog)
    log.info('mo_fetch_catalog_today: %d préfixes d\'objets trouvés', len(catalog))
    return catalog


def _mo_visible_tonight():
    """
    Retourne les objets MO visibles depuis Tlemcen à 23h00 UTC (nuit locale),
    triés par altitude décroissante.
    """
    from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_body
    from astropy.time import Time
    import astropy.units as u

    location = EarthLocation(lat=OBSERVER_LAT*u.deg, lon=OBSERVER_LON*u.deg, height=OBSERVER_ALT_M*u.m)
    # 23:00 UTC = 00:00 locale Tlemcen (UTC+1)
    t_obs = Time(int(Time.now().jd) + 23/24.0, format='jd')
    frame = AltAz(obstime=t_obs, location=location)

    visible = []
    seen_labels = set()

    for prefix, info in _MO_OBJECT_CATALOG.items():
        try:
            if info.get('body'):
                if info['body'] == 'sun':
                    continue
                coord = get_body(info['body'], t_obs, location)
                altaz = coord.transform_to(frame)
                alt = float(altaz.alt.deg)
            elif info.get('ra') is not None:
                coord = SkyCoord(ra=info['ra']*u.deg, dec=info['dec']*u.deg, frame='icrs')
                altaz = coord.transform_to(frame)
                alt = float(altaz.alt.deg)
            else:
                continue
        except Exception:
            continue

        label = info['label']
        if alt > 20 and label not in seen_labels:
            seen_labels.add(label)
            visible.append({'prefix': prefix, 'alt': round(alt, 1), **info})

    visible.sort(key=lambda x: -x['alt'])
    return visible


def _mo_fits_to_jpg(fits_bytes, save_path):
    """Convertit des octets FITS en JPG avec étirement ZScale + colormap hot."""
    import io, numpy as np
    from astropy.io import fits as _fits
    from astropy.visualization import ZScaleInterval
    from PIL import Image

    with _fits.open(io.BytesIO(fits_bytes)) as hdul:
        data = hdul[0].data
        header = hdul[0].header
        captured_hdr = header.get('DATE-OBS', header.get('DATE', ''))

    if data is None:
        raise ValueError('FITS data vide')

    while hasattr(data, 'ndim') and data.ndim > 2:
        data = data[0]
    arr = np.nan_to_num(np.asarray(data, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)

    interval = ZScaleInterval()
    try:
        vmin, vmax = interval.get_limits(arr)
    except Exception:
        vmin = float(np.percentile(arr, 2))
        vmax = float(np.percentile(arr, 98))
    if vmax <= vmin:
        vmax = vmin + 1.0

    norm = np.clip((arr - vmin) / (vmax - vmin), 0.0, 1.0)
    r = np.clip(norm * 255,       0, 255).astype(np.uint8)
    g = np.clip(norm * 155,       0, 255).astype(np.uint8)
    b = np.clip(norm * 55  - 10,  0, 255).astype(np.uint8)

    pil = Image.fromarray(np.stack([r, g, b], axis=2), 'RGB').resize((600, 600), Image.LANCZOS)
    pil.save(save_path, 'JPEG', quality=92, optimize=True)
    return captured_hdr
