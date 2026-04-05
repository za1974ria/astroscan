"""
Couche TLE locale prioritaire (data_core/tle) — réseau en secours, jamais d’écrasement par du vide.
Ne dépend pas de station_web (évite imports circulaires).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

_log = logging.getLogger("astroscan.tle")

DEFAULT_MAX_AGE_SECONDS = 6 * 3600
BUNDLE_NAME = "bundle.json"
ACTIVE_TLE_NAME = "active.tle"


def _data_core_tle_dir(station_root: str) -> Path:
    return Path(station_root) / "data_core" / "tle"


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_tle_fresh(last_refresh_iso: Optional[str], max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> bool:
    dt = _parse_iso(last_refresh_iso)
    if dt is None:
        return False
    try:
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age >= 0 and age <= float(max_age_seconds)
    except Exception:
        return False


def _parse_three_line_tle_lines(raw_lines: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    i = 0
    while i + 2 < len(raw_lines):
        name = raw_lines[i].strip()
        l1 = raw_lines[i + 1].strip()
        l2 = raw_lines[i + 2].strip()
        if l1.startswith("1 ") and l2.startswith("2 "):
            out.append(
                {
                    "name": name,
                    "norad_cat_id": None,
                    "tle_line1": l1,
                    "tle_line2": l2,
                    "object_type": None,
                    "epoch": None,
                }
            )
            i += 3
            continue
        i += 1
    return out


def _parse_active_tle_file(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return []
        raw = path.read_text(encoding="utf-8", errors="ignore")
        lines = [ln.strip() for ln in raw.splitlines() if ln and ln.strip()]
        return _parse_three_line_tle_lines(lines)
    except Exception:
        return []


def load_local_tle(station_root: str) -> Optional[Dict[str, Any]]:
    """
    Lit data_core/tle/bundle.json puis data_core/tle/active.tle.
    Retourne un bundle {status, source, last_refresh_iso, count, items, error} ou None.
    """
    d = _data_core_tle_dir(station_root)
    try:
        bundle_path = d / BUNDLE_NAME
        if bundle_path.is_file():
            raw = bundle_path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
            if isinstance(data, dict):
                items = data.get("items") or []
                if isinstance(items, list) and len(items) > 0:
                    return {
                        "status": str(data.get("status") or "cached"),
                        "source": str(data.get("source") or "data_core_bundle"),
                        "last_refresh_iso": data.get("last_refresh_iso"),
                        "count": len(items),
                        "items": items,
                        "error": data.get("error"),
                    }
    except Exception:
        pass
    try:
        atle = d / ACTIVE_TLE_NAME
        if atle.is_file() and atle.stat().st_size > 0:
            parsed = _parse_active_tle_file(atle)
            if parsed:
                try:
                    mtime = atle.stat().st_mtime
                    ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                except Exception:
                    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                return {
                    "status": "cached",
                    "source": "data_core_active_tle",
                    "last_refresh_iso": ts,
                    "count": len(parsed),
                    "items": parsed,
                    "error": None,
                }
    except Exception:
        pass
    return None


def save_tle_local(station_root: str, bundle: Dict[str, Any]) -> bool:
    """
    Écrit data_core/tle/bundle.json de façon atomique.
    Ne remplace pas un fichier non vide par un bundle sans items.
    """
    try:
        items = bundle.get("items") if isinstance(bundle, dict) else None
        if not isinstance(items, list):
            items = []
        d = _data_core_tle_dir(station_root)
        d.mkdir(parents=True, exist_ok=True)
        dest = d / BUNDLE_NAME
        if len(items) == 0 and dest.is_file():
            try:
                prev = json.loads(dest.read_text(encoding="utf-8", errors="replace"))
                if isinstance(prev, dict) and isinstance(prev.get("items"), list) and len(prev["items"]) > 0:
                    _log.warning("TLE save skipped: refusing empty overwrite of existing bundle")
                    return False
            except Exception:
                pass
            return False
        if len(items) == 0:
            return False
        to_write = {
            "status": bundle.get("status") or "cached",
            "source": bundle.get("source") or "data_core",
            "last_refresh_iso": bundle.get("last_refresh_iso"),
            "count": len(items),
            "items": items,
            "error": bundle.get("error"),
        }
        fd, tmp = tempfile.mkstemp(prefix="tle_", suffix=".json", dir=str(d))
        try:
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(to_write, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(dest))
            return True
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        _log.warning("TLE save_tle_local failed: %s", e)
        return False


def fetch_remote_tle_safe(
    url: str,
    normalize_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    timeout: float = 5.0,
    max_items: int = 1000,
) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            data = data.get("member") if isinstance(data, dict) else []
        items: List[Dict[str, Any]] = []
        for rec in data:
            norm = normalize_fn(rec or {})
            if norm:
                items.append(norm)
        if len(items) > max_items:
            items = items[:max_items]
        if not items:
            return None
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "status": "connected",
            "source": "CelesTrak GP active JSON",
            "last_refresh_iso": ts,
            "count": len(items),
            "items": items,
            "error": None,
        }
    except Exception:
        return None


def _load_legacy_json_cache(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            return None
        items = data.get("items") or []
        if not isinstance(items, list) or not items:
            return None
        return {
            "status": str(data.get("status") or "cached"),
            "source": str(data.get("source") or "legacy_json_cache"),
            "last_refresh_iso": data.get("last_refresh_iso"),
            "count": len(items),
            "items": items,
            "error": data.get("error"),
        }
    except Exception:
        return None


def bootstrap_from_local_layers(station_root: str) -> Optional[Dict[str, Any]]:
    """
    Ordre : data_core bundle → data_core active.tle → data/tle_active_cache.json → data/tle/active.tle
    """
    b = load_local_tle(station_root)
    if b and b.get("items"):
        return b
    try:
        legacy_json = Path(station_root) / "data" / "tle_active_cache.json"
        x = _load_legacy_json_cache(legacy_json)
        if x and x.get("items"):
            return x
    except Exception:
        pass
    try:
        legacy_tle = Path(station_root) / "data" / "tle" / "active.tle"
        parsed = _parse_active_tle_file(legacy_tle)
        if parsed:
            return {
                "status": "cached",
                "source": "legacy_active_tle",
                "last_refresh_iso": None,
                "count": len(parsed),
                "items": parsed,
                "error": None,
            }
    except Exception:
        pass
    return None


def get_tle_safe(
    station_root: str,
    remote_url: str,
    normalize_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    *,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    skip_remote: bool = False,
) -> Dict[str, Any]:
    """
    Orchestration : local data_core frais → sinon réseau → sinon caches locaux (stale / legacy).
    Ne lève pas d’exception.
    """
    out: Dict[str, Any] = {
        "ok": False,
        "bundle": None,
        "provenance": "none",
        "skipped_network": False,
    }
    try:
        local = load_local_tle(station_root)
        if local and local.get("items") and is_tle_fresh(local.get("last_refresh_iso"), max_age_seconds):
            out["ok"] = True
            out["bundle"] = local
            out["provenance"] = "data_core_fresh"
            out["skipped_network"] = True
            _log.info("TLE loaded from cache")
            return out
        if skip_remote:
            if local and local.get("items"):
                out["ok"] = True
                out["bundle"] = local
                out["provenance"] = "data_core_stale" if local else "none"
                _log.info("TLE loaded from cache")
                return out
            fb = bootstrap_from_local_layers(station_root)
            if fb and fb.get("items"):
                out["ok"] = True
                out["bundle"] = fb
                out["provenance"] = "legacy_bootstrap"
                _log.info("TLE loaded from cache")
            return out
        remote = fetch_remote_tle_safe(remote_url, normalize_fn)
        if remote and remote.get("items"):
            save_tle_local(station_root, remote)
            out["ok"] = True
            out["bundle"] = remote
            out["provenance"] = "remote"
            _log.info("TLE refreshed from remote")
            return out
        if local and local.get("items"):
            out["ok"] = True
            out["bundle"] = local
            out["provenance"] = "data_core_stale"
            _log.info("TLE fallback used")
            return out
        fb = bootstrap_from_local_layers(station_root)
        if fb and fb.get("items"):
            out["ok"] = True
            out["bundle"] = fb
            out["provenance"] = "legacy_bootstrap"
            _log.info("TLE fallback used")
        return out
    except Exception:
        return out


def fresh_bundle_for_skip_network(station_root: str, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> Optional[Dict[str, Any]]:
    """Si data_core est frais, retourne le bundle pour court-circuiter le fetch réseau."""
    try:
        b = load_local_tle(station_root)
        if b and b.get("items") and is_tle_fresh(b.get("last_refresh_iso"), max_age_seconds):
            return b
    except Exception:
        pass
    return None


def merge_bundle_into_tle_cache_dict(
    target: Dict[str, Any],
    bundle: Dict[str, Any],
    *,
    preserve_error: Optional[str] = None,
) -> None:
    """Met à jour un dict style TLE_CACHE en place (pas d’import Flask)."""
    try:
        items = bundle.get("items") if isinstance(bundle, dict) else None
        if not isinstance(items, list) or not items:
            return
        target["status"] = bundle.get("status") or target.get("status") or "cached"
        target["source"] = bundle.get("source") or target.get("source")
        target["last_refresh_iso"] = bundle.get("last_refresh_iso") or target.get("last_refresh_iso")
        target["count"] = len(items)
        target["items"] = items
        if preserve_error is not None:
            target["error"] = preserve_error
        elif bundle.get("error") is not None:
            target["error"] = bundle.get("error")
    except Exception:
        pass
