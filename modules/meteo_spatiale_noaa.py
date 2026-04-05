# -*- coding: utf-8 -*-
"""Agrégation temps réel NOAA SWPC / GOES pour AstroScan-Chohra."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

UA = {"User-Agent": "ASTRO-SCAN/1.0 orbital-chohra@gmail.com"}
TIMEOUT = 18

NOAA_JSON = "https://services.swpc.noaa.gov/json"
URL_KP = f"{NOAA_JSON}/planetary_k_index_1m.json"
URL_WIND = f"{NOAA_JSON}/rtsw/rtsw_wind_1m.json"
URL_MAG = f"{NOAA_JSON}/rtsw/rtsw_mag_1m.json"
URL_FLARES_7D = f"{NOAA_JSON}/goes/primary/xray-flares-7-day.json"
URL_ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"


def _get_json(url: str) -> Any:
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _parse_flare_class(s: Optional[str]) -> Optional[Tuple[str, float]]:
    if not s or not isinstance(s, str):
        return None
    m = re.match(r"^([ABCMX])(\d+(?:\.\d+)?)", s.strip().upper())
    if not m:
        return None
    return m.group(1), float(m.group(2))


def _kp_status_fr(kp: float) -> str:
    if kp <= 3:
        return "CALME (VERT)"
    if kp <= 5:
        return "MODÉRÉ (JAUNE)"
    if kp <= 7:
        return "ACTIF (ORANGE)"
    return "SÉVÈRE (ROUGE)"


def _impact_fr(kp: float) -> str:
    if kp <= 3:
        return "Conditions calmes — orbites basses normales."
    if kp <= 5:
        return "Perturbations mineures possibles sur les orbites basses."
    if kp <= 7:
        return "Drag atmosphérique et erreurs GPS possibles."
    return "Risque élevé pour satellites et infrastructures (courants telluriques)."


def _extract_kp(rows: List[dict]) -> Dict[str, Any]:
    if not rows:
        return {}
    last = rows[-1]
    est = last.get("estimated_kp")
    if est is None:
        est = float(last.get("kp_index") or 0)
    else:
        est = float(est)
    return {
        "kp_index": round(est, 2),
        "kp_time_tag": last.get("time_tag"),
        "kp_raw": last.get("kp"),
    }


def _extract_wind(rows: List[dict]) -> Dict[str, Any]:
    if not rows:
        return {}
    # Préférer la source active la plus récente
    for row in reversed(rows):
        if row.get("active") and row.get("proton_speed") is not None:
            return {
                "solar_wind_speed_kms": round(float(row["proton_speed"]), 1),
                "solar_wind_density_cm3": (
                    round(float(row["proton_density"]), 2) if row.get("proton_density") is not None else None
                ),
                "solar_wind_source": row.get("source") or "—",
                "solar_wind_time_tag": row.get("time_tag"),
            }
    row = rows[-1]
    return {
        "solar_wind_speed_kms": round(float(row.get("proton_speed") or 0), 1),
        "solar_wind_density_cm3": (
            round(float(row["proton_density"]), 2) if row.get("proton_density") is not None else None
        ),
        "solar_wind_source": row.get("source") or "—",
        "solar_wind_time_tag": row.get("time_tag"),
    }


def _extract_mag(rows: List[dict]) -> Dict[str, Any]:
    if not rows:
        return {}
    for row in reversed(rows):
        if row.get("active") and row.get("bz_gsm") is not None:
            bz = float(row["bz_gsm"])
            return {
                "bz_gsm_nt": round(bz, 2),
                "bt_nt": round(float(row.get("bt") or 0), 2) if row.get("bt") is not None else None,
                "mag_source": row.get("source") or "—",
                "mag_time_tag": row.get("time_tag"),
                "bz_interpretation": "calme (champ nordward)" if bz > 0 else "à risque (champ sudward)",
            }
    row = rows[-1]
    bz = float(row.get("bz_gsm") or 0)
    return {
        "bz_gsm_nt": round(bz, 2),
        "bt_nt": round(float(row.get("bt") or 0), 2) if row.get("bt") is not None else None,
        "mag_source": row.get("source") or "—",
        "mag_time_tag": row.get("time_tag"),
        "bz_interpretation": "calme (champ nordward)" if bz > 0 else "à risque (champ sudward)",
    }


def _flare_counts_and_charts(flares: List[dict]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cut24 = now - timedelta(hours=24)
    cut7d = now - timedelta(days=7)
    counts = {"A": 0, "B": 0, "C": 0, "M": 0, "X": 0}
    per_day: Dict[str, int] = defaultdict(int)
    timeline_mx: List[Dict[str, Any]] = []

    for ev in flares:
        if not isinstance(ev, dict):
            continue
        mt = ev.get("max_time") or ev.get("begin_time") or ev.get("time_tag")
        if not mt:
            continue
        try:
            t = datetime.fromisoformat(mt.replace("Z", "+00:00"))
        except ValueError:
            continue
        mc = ev.get("max_class") or ""
        parsed = _parse_flare_class(mc)
        if t >= cut24 and parsed:
            letter = parsed[0]
            if letter in counts:
                counts[letter] += 1
        if t >= cut7d:
            day_key = t.strftime("%Y-%m-%d")
            per_day[day_key] += 1
            if parsed and parsed[0] in ("M", "X"):
                timeline_mx.append(
                    {
                        "time": mt,
                        "class": mc,
                        "max_xrlong": ev.get("max_xrlong"),
                    }
                )

    timeline_mx.sort(key=lambda x: x["time"], reverse=True)
    chart_labels = sorted(per_day.keys())
    chart_values = [per_day[k] for k in chart_labels]
    return {
        "flare_counts_24h": counts,
        "flare_chart_7d_labels": chart_labels,
        "flare_chart_7d_counts": chart_values,
        "flare_timeline_mx": timeline_mx[:24],
    }


def _active_alerts(max_items: int = 15) -> List[Dict[str, Any]]:
    try:
        data = _get_json(URL_ALERTS)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data[: max_items * 4]:
        if not isinstance(item, dict):
            continue
        msg = (item.get("message") or item.get("msg") or "").replace("\r\n", " ").strip()
        if not msg:
            continue
        issued = str(item.get("issue_datetime") or item.get("issued") or "")[:40]
        out.append(
            {
                "product_id": item.get("product_id"),
                "issued": issued,
                "message": msg[:500],
                "active": True,
            }
        )
        if len(out) >= max_items:
            break
    return out


def build_meteo_spatiale_payload() -> Dict[str, Any]:
    """Payload complet pour /api/meteo-spatiale (cache 60 s côté app)."""
    payload: Dict[str, Any] = {
        "statut_magnetosphere": "Indisponible",
        "kp_index": None,
        "impact_orbital": "",
        "source": "NOAA SWPC (live)",
        "noaa_urls": {
            "kp": URL_KP,
            "wind": URL_WIND,
            "mag": URL_MAG,
            "flares_7d": URL_FLARES_7D,
            "alerts": URL_ALERTS,
        },
    }
    try:
        kp_rows = _get_json(URL_KP)
        if isinstance(kp_rows, list) and kp_rows:
            kpd = _extract_kp(kp_rows)
            payload.update(kpd)
            kp = float(kpd.get("kp_index") or 0)
            payload["statut_magnetosphere"] = _kp_status_fr(kp)
            payload["impact_orbital"] = _impact_fr(kp)
    except Exception as e:
        payload["kp_error"] = str(e)[:200]

    try:
        wind_rows = _get_json(URL_WIND)
        if isinstance(wind_rows, list) and wind_rows:
            payload.update(_extract_wind(wind_rows))
    except Exception as e:
        payload["wind_error"] = str(e)[:200]

    try:
        mag_rows = _get_json(URL_MAG)
        if isinstance(mag_rows, list) and mag_rows:
            payload.update(_extract_mag(mag_rows))
    except Exception as e:
        payload["mag_error"] = str(e)[:200]

    try:
        flares = _get_json(URL_FLARES_7D)
        if isinstance(flares, list):
            payload["flares_7day_count"] = len(flares)
            payload.update(_flare_counts_and_charts(flares))
    except Exception as e:
        payload["flares_error"] = str(e)[:200]
        payload["flare_counts_24h"] = {"A": 0, "B": 0, "C": 0, "M": 0, "X": 0}
        payload["flare_chart_7d_labels"] = []
        payload["flare_chart_7d_counts"] = []
        payload["flare_timeline_mx"] = []

    try:
        payload["alerts_active"] = _active_alerts(15)
    except Exception:
        payload["alerts_active"] = []

    payload["mise_a_jour_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    payload["alert_level_mx"] = (payload.get("flare_counts_24h") or {}).get("M", 0) + (
        payload.get("flare_counts_24h") or {}
    ).get("X", 0)

    return payload
