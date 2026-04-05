"""
NASA SkyView résilient : fetch HEASARC, snapshot data_core/skyview/, fallback propre.
Sans dépendance Flask — GIF validé comme payload (magic bytes + taille minimale).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger("astroscan.skyview")

SKYVIEW_BASE = "https://skyview.gsfc.nasa.gov/current/cgi/runquery.pl"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_AGE_SECONDS = 86400.0  # 24 h
DEFAULT_USER_AGENT = "AstroScan/1.0"
MIN_GIF_BYTES = 1000


def _skyview_dir(station_root: str) -> Path:
    return Path(station_root) / "data_core" / "skyview"


def build_skyview_url(
    coords: str,
    survey: str,
    size_deg: float,
    pixels: int,
) -> str:
    """Même construction que skyview_module (Position, Survey, Return=GIF, etc.)."""
    params = (
        f"?Position={coords}"
        f"&Survey={survey.replace(' ', '+')}"
        f"&Coordinates=J2000"
        f"&Return=GIF"
        f"&Size={size_deg}"
        f"&Pixels={pixels}"
        f"&scaling=Log"
        f"&resolver=SIMBAD-NED"
        f"&Deedger=_skip_"
        f"&Projection=Tan"
    )
    return SKYVIEW_BASE + params


def cache_key_string(
    target_id: str,
    coords: str,
    survey: str,
    size_deg: float,
    pixels: int,
) -> str:
    return f"{target_id}|{coords}|{survey}|{size_deg}|{pixels}"


def cache_key_hash(cache_key: str) -> str:
    return hashlib.sha256(cache_key.encode("utf-8")).hexdigest()


def parse_skyview_payload(data: Optional[bytes]) -> bool:
    """True si octets ressemblent à un GIF SkyView exploitable (pas page HTML d’erreur)."""
    try:
        if not data or len(data) < MIN_GIF_BYTES:
            return False
        head = data[:6]
        return head in (b"GIF87a", b"GIF89a")
    except Exception:
        return False


def fetch_remote_skyview(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional[bytes]:
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def is_skyview_snapshot_fresh(
    fetched_at_iso: Optional[str],
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    if not fetched_at_iso or not isinstance(fetched_at_iso, str):
        return False
    s = fetched_at_iso.strip()
    if not s:
        return False
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return 0 <= age <= float(max_age_seconds)
    except Exception:
        return False


def load_skyview_snapshot_disk(
    station_root: str,
    key_hash: str,
) -> Optional[Dict[str, Any]]:
    """
    Lit {hash}.gif + {hash}.meta.json.
    Retourne {gif_bytes, meta_dict} ou None si absent / invalide.
    """
    try:
        d = _skyview_dir(station_root)
        gif_p = d / f"{key_hash}.gif"
        meta_p = d / f"{key_hash}.meta.json"
        if not gif_p.is_file() or not meta_p.is_file():
            return None
        raw_meta = json.loads(meta_p.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(raw_meta, dict):
            return None
        data = gif_p.read_bytes()
        if not parse_skyview_payload(data):
            return None
        return {"gif_bytes": data, "meta": raw_meta}
    except Exception:
        return None


def save_skyview_snapshot_disk(
    station_root: str,
    key_hash: str,
    cache_key: str,
    gif_bytes: bytes,
    *,
    target_id: str,
    survey: str,
    size_deg: float,
    pixels: int,
    coords: str,
    fetched_at_iso: str,
) -> bool:
    """Écriture atomique ; refuse un GIF invalide."""
    try:
        if not parse_skyview_payload(gif_bytes):
            _log.warning("SKYVIEW snapshot save skipped: invalid payload")
            return False
        d = _skyview_dir(station_root)
        d.mkdir(parents=True, exist_ok=True)
        to_meta = {
            "cache_key": cache_key,
            "target_id": target_id,
            "survey": survey,
            "size_deg": size_deg,
            "pixels": pixels,
            "coords": coords,
            "fetched_at_iso": fetched_at_iso,
        }
        fd_g, tmp_g = tempfile.mkstemp(prefix="sv_", suffix=".gif", dir=str(d))
        tmp_m: Optional[str] = None
        try:
            os.close(fd_g)
            with open(tmp_g, "wb") as f:
                f.write(gif_bytes)
            fd_m, tmp_m = tempfile.mkstemp(prefix="sv_", suffix=".json", dir=str(d))
            os.close(fd_m)
            with open(tmp_m, "w", encoding="utf-8") as f:
                json.dump(to_meta, f, ensure_ascii=False, indent=2)
            os.replace(tmp_g, str(d / f"{key_hash}.gif"))
            os.replace(tmp_m, str(d / f"{key_hash}.meta.json"))
            return True
        except Exception:
            try:
                os.unlink(tmp_g)
            except Exception:
                pass
            if tmp_m:
                try:
                    os.unlink(tmp_m)
                except Exception:
                    pass
            raise
    except Exception as e:
        _log.warning("SKYVIEW snapshot save failed: %s", e)
        return False


def get_skyview_safe(
    station_root: str,
    target_id: str,
    coords: str,
    survey: str,
    size_deg: float,
    pixels: int,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
) -> Dict[str, Any]:
    """
    A. Fetch NASA → GIF valide → snapshot disque.
    B. Sinon snapshot local (même périmé) si GIF valide.
    C. Sinon fallback (pas d’octets image).

    Retour commun :
      ok, gif_bytes, fetch_source, stale, fetched_at_iso, error, cache_key, cache_key_hash
    """
    ck = cache_key_string(target_id, coords, survey, size_deg, pixels)
    kh = cache_key_hash(ck)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    last_err: Optional[str] = None

    url = build_skyview_url(coords, survey, size_deg, pixels)
    remote = fetch_remote_skyview(url, timeout=timeout, user_agent=user_agent)
    if remote is None:
        last_err = "remote_unavailable"
    elif not parse_skyview_payload(remote):
        last_err = "invalid_payload"
        remote = None

    if remote is not None:
        save_skyview_snapshot_disk(
            station_root,
            kh,
            ck,
            remote,
            target_id=target_id,
            survey=survey,
            size_deg=size_deg,
            pixels=pixels,
            coords=coords,
            fetched_at_iso=now_iso,
        )
        _log.info("SKYVIEW refreshed")
        return {
            "ok": True,
            "gif_bytes": remote,
            "fetch_source": "remote",
            "stale": False,
            "fetched_at_iso": now_iso,
            "error": None,
            "cache_key": ck,
            "cache_key_hash": kh,
            "skyview_url": url,
        }

    snap = load_skyview_snapshot_disk(station_root, kh)
    if snap and isinstance(snap.get("gif_bytes"), (bytes, bytearray)):
        meta = snap.get("meta") if isinstance(snap.get("meta"), dict) else {}
        fa = meta.get("fetched_at_iso") if isinstance(meta, dict) else None
        stale = not is_skyview_snapshot_fresh(
            fa if isinstance(fa, str) else None,
            max_age_seconds=max_age_seconds,
        )
        _log.info("SKYVIEW loaded from cache")
        return {
            "ok": True,
            "gif_bytes": bytes(snap["gif_bytes"]),
            "fetch_source": "cache_local",
            "stale": stale,
            "fetched_at_iso": fa if isinstance(fa, str) else None,
            "error": last_err,
            "cache_key": ck,
            "cache_key_hash": kh,
            "skyview_url": url,
        }

    _log.info("SKYVIEW fallback used")
    return {
        "ok": False,
        "gif_bytes": None,
        "fetch_source": "fallback_static",
        "stale": True,
        "fetched_at_iso": None,
        "error": last_err or "skyview_unavailable",
        "cache_key": ck,
        "cache_key_hash": kh,
        "skyview_url": url,
    }


def get_skyview_status_summary(
    station_root: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    pixels: int = 128,
) -> Dict[str, Any]:
    """
    État synthétique pour agrégation (ex. /api/system-status).
    Délègue entièrement à get_skyview_safe (cible canonique M42 / DSS2 Red, GIF réduit).
    """
    r = get_skyview_safe(
        station_root,
        "M42",
        "83.8221,-5.3911",
        "DSS2 Red",
        0.5,
        pixels,
        timeout=timeout,
    )
    if r.get("ok"):
        status = "ok" if r.get("fetch_source") == "remote" else "cache"
        return {
            "status": status,
            "source": r.get("fetch_source") or "cache_local",
            "stale": bool(r.get("stale")),
        }
    return {
        "status": "fallback",
        "source": "fallback_static",
        "stale": True,
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    root = str(Path(__file__).resolve().parents[1])
    # Test parse
    assert parse_skyview_payload(None) is False
    assert parse_skyview_payload(b"<html>") is False
    assert parse_skyview_payload(b"GIF89a" + b"x" * MIN_GIF_BYTES) is True
    # Test get (réseau optionnel)
    r = get_skyview_safe(root, "M42", "83.8221,-5.3911", "DSS2 Red", 0.5, 256)
    print("get_skyview_safe M42:", {k: r[k] for k in r if k != "gif_bytes"})
    if r.get("gif_bytes"):
        print("gif len:", len(r["gif_bytes"]))
    sys.exit(0 if r.get("ok") or r.get("fetch_source") == "fallback_static" else 1)
