# -*- coding: utf-8 -*-
"""
Telescope image downloader for AstroScan.
Downloads images from Hubble, JWST, ESO and saves to data/skyview for Digital Lab pipeline.
"""
import os
import json
import time
from datetime import datetime, timezone

from modules.astro_validation import (
    is_valid_astro_image,
    normalize_metadata,
)
from modules.space_sources.robotic_telescopes import (
    fetch_lco_observations,
    fetch_microobservatory_images,
    fetch_skynet_images,
    fetch_noirlab_images,
)


def _json_from_body(body):
    """Parse JSON depuis bytes/str ; None si HTML ou vide (évite bruit dans les logs)."""
    if body is None:
        return None
    if isinstance(body, bytes):
        s = body.decode("utf-8", errors="replace").strip()
    else:
        s = (str(body) or "").strip()
    if len(s) < 2 or s[0] not in "[{":
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _safe_retrieve(url, path, timeout=20):
    """Download URL to path. Returns True on success."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan-Telescope/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def _write_metadata(metadata_dir, filename, meta):
    """Write metadata JSON. Does not raise."""
    try:
        os.makedirs(metadata_dir, exist_ok=True)
        path = os.path.join(metadata_dir, filename + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception:
        pass


def _log_rejected(logs_dir, raw_meta, reason):
    """Append rejected image information to a JSON log file."""
    try:
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, "rejected_images.json")
        record = {
            "metadata": raw_meta,
            "reason": reason,
            "timestamp": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        # Append as JSON lines to keep file simple
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        # Logging failures must never break collectors
        pass


def download_hubble_images(raw_images_dir, metadata_dir):
    """Download images from Hubble API to raw_images_dir. Only validated astronomy images are saved."""
    try:
        import urllib.request
        os.makedirs(raw_images_dir, exist_ok=True)
        logs_dir = os.path.join(os.path.dirname(raw_images_dir), "logs")
        base_url = "https://hubblesite.org/api/v3"
        index_url = base_url + "/images?page=1"
        req = urllib.request.Request(index_url, headers={"User-Agent": "AstroScan-Telescope/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            images = _json_from_body(resp.read())
        if not isinstance(images, list):
            return
        for img in images[:5]:
            img_id = img.get("id")
            if not img_id:
                continue
            filename = f"hubble_{img_id}.jpg"
            path = os.path.join(raw_images_dir, filename)
            if os.path.exists(path):
                continue
            try:
                detail_url = f"{base_url}/image/{img_id}"
                dreq = urllib.request.Request(detail_url, headers={"User-Agent": "AstroScan-Telescope/1.0"})
                with urllib.request.urlopen(dreq, timeout=15) as dresp:
                    detail = _json_from_body(dresp.read())
                if not isinstance(detail, dict):
                    continue
                files = detail.get("image_files") or []
                if not files:
                    continue
                file_url = files[-1].get("file_url")
                if not file_url:
                    continue
                raw_meta = {
                    "source": "HUBBLE",
                    "title": detail.get("name", "") or "",
                    "description": detail.get("description", "") or "",
                    "keywords": detail.get("keywords", []) or [],
                    "collection": detail.get("collection", "") or "",
                    "telescope": "Hubble Space Telescope",
                    "mission": detail.get("mission", "") or "",
                    "object_name": detail.get("name", "") or detail.get("mission", ""),
                    "observation_date": detail.get("release_date", "") or "",
                    "original_url": file_url,
                }
                ok, reason = is_valid_astro_image(raw_meta)
                if not ok:
                    _log_rejected(logs_dir, raw_meta, reason)
                    continue
                if _safe_retrieve(file_url, path):
                    meta = normalize_metadata(
                        raw_meta,
                        source_provider="HUBBLE",
                        local_filename=filename,
                        validation_status="accepted",
                        reason=None,
                    )
                    meta["downloaded"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    _write_metadata(metadata_dir, filename, meta)
            except Exception:
                continue
    except Exception:
        pass


def download_jwst_images(raw_images_dir, metadata_dir):
    """Download images from JWST public feed to raw_images_dir. Only validated astronomy images are saved."""
    try:
        import urllib.request
        import re
        os.makedirs(raw_images_dir, exist_ok=True)
        logs_dir = os.path.join(os.path.dirname(raw_images_dir), "logs")
        urls_to_try = [
            "https://webbtelescope.org/api/v1/images",
            "https://stsci.edu/files/live/sites/www/home/news/jwst/_documents/",
        ]
        seen_urls = set()
        for base in urls_to_try:
            try:
                req = urllib.request.Request(base, headers={"User-Agent": "AstroScan-Telescope/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode(errors="replace")
                for m in re.finditer(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', body, re.I):
                    img_url = m.group(0).split("'")[0].split('"')[0]
                    if img_url in seen_urls:
                        continue
                    seen_urls.add(img_url)
                    ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
                    filename = f"jwst_{int(time.time())}_{len(seen_urls)}{ext}"
                    path = os.path.join(raw_images_dir, filename)
                    if os.path.exists(path):
                        continue
                    raw_meta = {
                        "source": "JWST",
                        "title": "",
                        "description": "",
                        "keywords": [],
                        "collection": "",
                        "telescope": "James Webb Space Telescope",
                        "mission": "",
                        "object_name": "JWST",
                        "observation_date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                        "original_url": img_url,
                    }
                    ok, reason = is_valid_astro_image(raw_meta)
                    if not ok:
                        _log_rejected(logs_dir, raw_meta, reason)
                        continue
                    if _safe_retrieve(img_url, path):
                        meta = normalize_metadata(
                            raw_meta,
                            source_provider="JWST",
                            local_filename=filename,
                            validation_status="accepted",
                            reason=None,
                        )
                        meta["downloaded"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
                        _write_metadata(metadata_dir, filename, meta)
                    if len(seen_urls) >= 3:
                        return
            except Exception:
                continue
    except Exception:
        pass


def download_eso_images(raw_images_dir, metadata_dir):
    """Download images from ESO public feed to raw_images_dir. Only validated astronomy images are saved."""
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        os.makedirs(raw_images_dir, exist_ok=True)
        logs_dir = os.path.join(os.path.dirname(raw_images_dir), "logs")
        feed_url = "https://www.eso.org/public/images/feed/"
        req = urllib.request.Request(feed_url, headers={"User-Agent": "AstroScan-Telescope/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode(errors="replace")
        root = ET.fromstring(body)
        ns = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/", "rss": "http://purl.org/rss/1.0/"}
        count = 0
        for item in root.findall(".//item") or root.findall(".//atom:entry", ns) or []:
            if count >= 3:
                break
            url = None
            title = ""
            for enc in item.findall("enclosure") or item.findall(".//media:content", ns) or []:
                url = enc.get("url") or enc.get("{http://search.yahoo.com/mrss/}url")
                if url and (".jpg" in url.lower() or ".png" in url.lower() or ".jpeg" in url.lower()):
                    break
            if not url and item.find("link") is not None:
                url = item.find("link").text or item.find("link").get("href")
            if not url:
                continue
            title_el = item.find("title") or item.find("atom:title", ns)
            if title_el is not None and title_el.text:
                title = title_el.text.strip()[:200]
            ext = ".jpg" if ".jpg" in url.lower() else ".png"
            filename = f"eso_{int(time.time())}_{count}{ext}"
            path = os.path.join(raw_images_dir, filename)
            if os.path.exists(path):
                count += 1
                continue
            raw_meta = {
                "source": "ESO",
                "title": title or "",
                "description": "",
                "keywords": [],
                "collection": "",
                "telescope": "ESO",
                "mission": "",
                "object_name": title or "ESO",
                "observation_date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                "original_url": url,
            }
            ok, reason = is_valid_astro_image(raw_meta)
            if not ok:
                _log_rejected(logs_dir, raw_meta, reason)
                continue
            if _safe_retrieve(url, path):
                meta = normalize_metadata(
                    raw_meta,
                    source_provider="ESO",
                    local_filename=filename,
                    validation_status="accepted",
                    reason=None,
                )
                meta["downloaded"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
                _write_metadata(metadata_dir, filename, meta)
                count += 1
    except Exception:
        pass


def _vo_download_one(raw_images_dir, metadata_dir, logs_dir, obs, provider, filename_prefix, ext_from_url=True):
    """Helper: download one VO observation, validate, save or log. Returns True if saved."""
    image_url = (obs.get("image_url") or "").strip()
    if not image_url:
        return False
    try:
        if ext_from_url:
            if ".fits.fz" in image_url or ".fits" in image_url:
                ext = ".fits.fz" if ".fits.fz" in image_url else ".fits"
            else:
                ext = ".jpg" if ".jpg" in image_url.lower() else ".png"
        else:
            ext = ".jpg"
        filename = "%s_%s%s" % (filename_prefix, int(time.time() * 1000), ext)
        path = os.path.join(raw_images_dir, filename)
        if os.path.exists(path):
            return False
        raw_meta = {
            "source": provider,
            "title": obs.get("title") or obs.get("object_name") or "",
            "description": "telescope observation",
            "keywords": ["telescope observation", "cosmos"],
            "collection": "",
            "telescope": obs.get("telescope") or "",
            "mission": "",
            "instrument": obs.get("instrument") or "",
            "object_name": obs.get("object_name") or "",
            "observation_date": obs.get("observation_date") or "",
            "original_url": image_url,
            "image_url": image_url,
            "ra": obs.get("ra"),
            "dec": obs.get("dec"),
            "exposure_time": obs.get("exposure_time"),
            "filter": obs.get("filter"),
        }
        ok, reason = is_valid_astro_image(raw_meta)
        if not ok:
            _log_rejected(logs_dir, raw_meta, reason)
            return False
        if not _safe_retrieve(image_url, path):
            return False
        meta = normalize_metadata(
            raw_meta,
            source_provider=provider,
            local_filename=filename,
            validation_status="accepted",
            reason=None,
        )
        meta["downloaded"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        _write_metadata(metadata_dir, filename, meta)
        return True
    except Exception:
        return False


def download_lco_images(raw_images_dir, metadata_dir):
    """Download Las Cumbres Observatory observations to raw_images_dir. Only validated images saved."""
    try:
        os.makedirs(raw_images_dir, exist_ok=True)
        logs_dir = os.path.join(os.path.dirname(raw_images_dir), "logs")
        observations = fetch_lco_observations(limit=3)
        for obs in observations:
            try:
                _vo_download_one(raw_images_dir, metadata_dir, logs_dir, obs, "LCO", "lco", ext_from_url=True)
            except Exception:
                continue
    except Exception:
        pass


def download_microobservatory_images(raw_images_dir, metadata_dir):
    """Download Harvard MicroObservatory images to raw_images_dir. Only validated images saved."""
    try:
        os.makedirs(raw_images_dir, exist_ok=True)
        logs_dir = os.path.join(os.path.dirname(raw_images_dir), "logs")
        observations = fetch_microobservatory_images(limit=3)
        for obs in observations:
            try:
                _vo_download_one(raw_images_dir, metadata_dir, logs_dir, obs, "MICROOBSERVATORY", "microobs", ext_from_url=True)
            except Exception:
                continue
    except Exception:
        pass


def download_skynet_images(raw_images_dir, metadata_dir):
    """Download Skynet Robotic Telescope images to raw_images_dir. Only validated images saved."""
    try:
        os.makedirs(raw_images_dir, exist_ok=True)
        logs_dir = os.path.join(os.path.dirname(raw_images_dir), "logs")
        observations = fetch_skynet_images(limit=3)
        for obs in observations:
            try:
                _vo_download_one(raw_images_dir, metadata_dir, logs_dir, obs, "SKYNET", "skynet", ext_from_url=True)
            except Exception:
                continue
    except Exception:
        pass


def download_noirlab_images(raw_images_dir, metadata_dir):
    """Download NOIRLab archive images to raw_images_dir. Only validated images saved."""
    try:
        os.makedirs(raw_images_dir, exist_ok=True)
        logs_dir = os.path.join(os.path.dirname(raw_images_dir), "logs")
        observations = fetch_noirlab_images(limit=3)
        for obs in observations:
            try:
                _vo_download_one(raw_images_dir, metadata_dir, logs_dir, obs, "NOIRLAB", "noirlab", ext_from_url=True)
            except Exception:
                continue
    except Exception:
        pass


def run_telescope_collector(raw_images_dir, metadata_dir):
    """Run all telescope downloaders. Saves only validated astronomy images to raw_images_dir."""
    try:
        download_hubble_images(raw_images_dir, metadata_dir)
    except Exception:
        pass
    try:
        download_jwst_images(raw_images_dir, metadata_dir)
    except Exception:
        pass
    try:
        download_eso_images(raw_images_dir, metadata_dir)
    except Exception:
        pass
    try:
        download_lco_images(raw_images_dir, metadata_dir)
    except Exception:
        pass
    try:
        download_microobservatory_images(raw_images_dir, metadata_dir)
    except Exception:
        pass
    try:
        download_skynet_images(raw_images_dir, metadata_dir)
    except Exception:
        pass
    try:
        download_noirlab_images(raw_images_dir, metadata_dir)
    except Exception:
        pass
