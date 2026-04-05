"""
Flux DSN résilient : fetch NASA, snapshot data_core/dsn/, fallback historique.
Sans dépendance Flask — parsing XML aligné sur station_web.api_dsn (historique).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("astroscan.dsn")

DEFAULT_DSN_URL = "https://eyes.nasa.gov/dsn/data/dsn.xml"
DEFAULT_TIMEOUT = 15.0
DEFAULT_USER_AGENT = "AstroScan/1.0"
DEFAULT_MAX_AGE_SECONDS = 900.0  # 15 min
SNAPSHOT_JSON_NAME = "last_snapshot.json"
RAW_XML_NAME = "dsn_last.xml"


def _dsn_dir(station_root: str) -> Path:
    return Path(station_root) / "data_core" / "dsn"


def _local_tag(tag: str) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def build_dsn_fallback_payload() -> Dict[str, Any]:
    """Même structure que le fallback historique de /api/dsn (stations + status)."""
    return {
        "stations": [
            {"friendlyName": "Goldstone (USA)", "name": "GDS", "dishes": []},
            {"friendlyName": "Madrid (Spain)", "name": "MDS", "dishes": []},
            {"friendlyName": "Canberra (Australia)", "name": "CDS", "dishes": []},
        ],
        "status": "fallback",
    }


def parse_dsn_xml_to_payload(xml_text: str) -> Dict[str, Any]:
    """
    Parse le XML NASA DSN → {"stations": [...]}.
    Lève Exception si XML invalide ou structure inattendue.
    """
    root = ET.fromstring(xml_text)
    stations: List[Dict[str, Any]] = []
    current_station: Optional[Dict[str, Any]] = None
    for elem in root:
        t = _local_tag(elem.tag)
        if t == "station":
            current_station = {
                "name": elem.get("name") or "",
                "friendlyName": elem.get("friendlyName") or elem.get("friendlyname") or "",
                "dishes": [],
            }
            stations.append(current_station)
        elif t == "dish" and current_station is not None:
            dish = {
                "name": elem.get("name") or "",
                "azimuth": elem.get("azimuthAngle") or elem.get("azimuth"),
                "elevation": elem.get("elevationAngle") or elem.get("elevation"),
                "activity": elem.get("activity") or "",
                "upSignals": [],
                "downSignals": [],
                "targets": [],
            }
            for child in elem:
                ct = _local_tag(child.tag)
                if ct == "upSignal":
                    dish["upSignals"].append(
                        {
                            "spacecraft": child.get("spacecraft") or "",
                            "power": child.get("power") or "",
                            "band": child.get("band") or "",
                            "active": child.get("active") or "",
                        }
                    )
                elif ct == "downSignal":
                    dish["downSignals"].append(
                        {
                            "spacecraft": child.get("spacecraft") or "",
                            "dataRate": child.get("dataRate") or child.get("datarate") or "",
                            "band": child.get("band") or "",
                            "active": child.get("active") or "",
                        }
                    )
                elif ct == "target":
                    dish["targets"].append(
                        {
                            "name": child.get("name") or "",
                            "uplegRange": child.get("uplegRange") or child.get("uplegrange") or "",
                            "rtlt": child.get("rtlt") or "",
                        }
                    )
            current_station["dishes"].append(dish)
    return {"stations": stations}


def fetch_remote_dsn_xml(
    url: str = DEFAULT_DSN_URL,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional[str]:
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def is_dsn_snapshot_fresh(fetched_at_iso: Optional[str], max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> bool:
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


def load_local_dsn_snapshot(station_root: str) -> Optional[Dict[str, Any]]:
    """Lit last_snapshot.json ; retourne dict avec stations + fetched_at_iso ou None."""
    try:
        p = _dsn_dir(station_root) / SNAPSHOT_JSON_NAME
        if not p.is_file():
            return None
        raw = p.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        st = data.get("stations")
        if not isinstance(st, list) or len(st) == 0:
            return None
        return {
            "stations": st,
            "fetched_at_iso": data.get("fetched_at_iso"),
        }
    except Exception:
        return None


def _snapshot_nonempty(stations: Any) -> bool:
    return isinstance(stations, list) and len(stations) > 0


def save_local_dsn_snapshot(
    station_root: str,
    payload: Dict[str, Any],
    raw_xml: Optional[str] = None,
) -> bool:
    """
    Écrit last_snapshot.json (atomique). Optionnellement dsn_last.xml.
    Ne remplace pas un snapshot valide par des stations vides.
    """
    try:
        stations = payload.get("stations") if isinstance(payload, dict) else None
        if not _snapshot_nonempty(stations):
            _log.warning("DSN snapshot save skipped: empty stations")
            return False
        d = _dsn_dir(station_root)
        d.mkdir(parents=True, exist_ok=True)
        dest = d / SNAPSHOT_JSON_NAME
        if dest.is_file():
            try:
                prev = json.loads(dest.read_text(encoding="utf-8", errors="replace"))
                if isinstance(prev, dict) and _snapshot_nonempty(prev.get("stations")):
                    if not _snapshot_nonempty(stations):
                        return False
            except Exception:
                pass
        fetched = payload.get("fetched_at_iso")
        if not fetched:
            fetched = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        to_write = {
            "stations": stations,
            "fetched_at_iso": fetched,
        }
        fd, tmp = tempfile.mkstemp(prefix="dsn_", suffix=".json", dir=str(d))
        try:
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(to_write, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(dest))
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        if raw_xml is not None and isinstance(raw_xml, str) and len(raw_xml) > 0:
            try:
                raw_path = d / RAW_XML_NAME
                fd2, tmp2 = tempfile.mkstemp(prefix="dsn_", suffix=".xml", dir=str(d))
                os.close(fd2)
                with open(tmp2, "w", encoding="utf-8") as f:
                    f.write(raw_xml)
                os.replace(tmp2, str(raw_path))
            except Exception:
                pass
        return True
    except Exception as e:
        _log.warning("DSN snapshot save failed: %s", e)
        return False


def get_dsn_safe(
    station_root: str,
    *,
    url: str = DEFAULT_DSN_URL,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
) -> Dict[str, Any]:
    """
    A. Fetch NASA → parse → sauvegarde snapshot si stations non vides.
    B. Sinon snapshot local si présent (metadata honnête).
    C. Sinon fallback historique.
    """
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    last_err: Optional[str] = None

    xml_text = fetch_remote_dsn_xml(url, timeout=timeout, user_agent=user_agent)
    if xml_text is None:
        last_err = "remote_unavailable"
    if xml_text is not None:
        try:
            parsed = parse_dsn_xml_to_payload(xml_text)
            stations = parsed.get("stations")
            if _snapshot_nonempty(stations):
                payload_save = {"stations": stations, "fetched_at_iso": now_iso}
                save_local_dsn_snapshot(station_root, payload_save, raw_xml=xml_text)
                _log.info("DSN refreshed from remote")
                return {
                    "stations": stations,
                    "status": "ok",
                    "source": "remote",
                    "stale": False,
                    "fetched_at_iso": now_iso,
                    "error": None,
                }
            last_err = "empty_stations"
        except Exception as ex:
            last_err = str(ex)[:300]

    snap = load_local_dsn_snapshot(station_root)
    if snap and _snapshot_nonempty(snap.get("stations")):
        fa = snap.get("fetched_at_iso")
        stale = not is_dsn_snapshot_fresh(fa, max_age_seconds=max_age_seconds)
        _log.info("DSN loaded from cache")
        out: Dict[str, Any] = {
            "stations": snap["stations"],
            "status": "cache",
            "source": "cache_local",
            "stale": stale,
            "fetched_at_iso": fa,
            "error": last_err,
        }
        return out

    _log.info("DSN fallback used")
    fb = build_dsn_fallback_payload()
    fb["source"] = "fallback_static"
    fb["stale"] = True
    fb["fetched_at_iso"] = None
    fb["error"] = last_err
    return fb
