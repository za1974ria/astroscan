"""MicroObservatory helpers — Harvard Smithsonian image directory scrape + FITS preview.

Extrait de station_web.py (PASS 15) pour permettre l'utilisation
par cameras_bp sans dépendance circulaire.

Sources :
    https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/
    https://mo-www.cfa.harvard.edu/ImageDirectory/<filename>
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.services.http_client import _curl_get

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
