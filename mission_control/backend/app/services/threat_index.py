"""Global Threat Index — single source of truth.

Cette implementation est l'unique source de calcul du Threat Index
diffuse sur :8000/ws. Toute autre formule dans le code base est un bug.

Formule auditable (cf. templates/methodology.html, section 4) :

    threat_index =
        0.35 * normalize(kp, 0, 9)
      + 0.20 * normalize(log10(xray_wm2), -8, -3)
      + 0.25 * seismic_score                          # deja 0..100 via /api/seismic
      + 0.10 * air_density_pct                        # deja 0..100 via /api/air-traffic
      + 0.10 * min(48, tle_age_hours) / 48 * 100      # freshness percent

Toutes les composantes sont normalisees en [0, 100]. Somme des poids = 1.0
=> threat_index [0, 100].

Mode degrade : si une composante est indisponible (collector down,
parsing failure, payload null), son poids est retire et les poids
restants sont renormalises pour resommer a 1.0. Le score reste donc
comparable au score live. Si toutes les composantes sont indisponibles,
index=None et state="unavailable" (aucun zero degisse en score reel).

Honnetete avant tout : data reelle OU etat honnete. JAMAIS de placeholder.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


WEIGHTS_NOMINAL: Dict[str, float] = {
    "kp": 0.35,
    "xray": 0.20,
    "seismic": 0.25,
    "air": 0.10,
    "tle_age": 0.10,
}

KP_RANGE = (0.0, 9.0)
XRAY_LOG_RANGE = (-8.0, -3.0)
TLE_AGE_HOURS_MAX = 48.0

_RAW_KEYS = {
    "kp": "kp",
    "xray": "xray_wm2",
    "seismic": "seismic_score",
    "air": "air_density_pct",
    "tle_age": "tle_age_hours",
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def normalize_kp(kp: Any) -> Optional[float]:
    """Kp [0..9] -> [0..100]. Linear."""
    v = _to_float(kp)
    if v is None:
        return None
    lo, hi = KP_RANGE
    return _clamp((v - lo) / (hi - lo) * 100.0, 0.0, 100.0)


def normalize_xray(xray_wm2: Any) -> Optional[float]:
    """GOES X-Ray long-band flux (W/m^2) -> [0..100] via log10 clamp [-8, -3].

    A-class quiet sun (~1e-8 W/m^2) -> 0
    X-class severe flare (~1e-3 W/m^2) -> 100

    Flux <= 0 (rare; quiet limit / sensor noise) clamps to 0 (no threat).
    """
    v = _to_float(xray_wm2)
    if v is None:
        return None
    if v <= 0:
        return 0.0
    log_flux = math.log10(v)
    lo, hi = XRAY_LOG_RANGE
    return _clamp((log_flux - lo) / (hi - lo) * 100.0, 0.0, 100.0)


def normalize_seismic(score: Any) -> Optional[float]:
    """USGS 24h seismic score (already 0..100 via /api/seismic). Clamp guard."""
    v = _to_float(score)
    if v is None:
        return None
    return _clamp(v, 0.0, 100.0)


def normalize_air(density_pct: Any) -> Optional[float]:
    """Air traffic density (already 0..100 via /api/air-traffic). Clamp guard."""
    v = _to_float(density_pct)
    if v is None:
        return None
    return _clamp(v, 0.0, 100.0)


def normalize_tle_age(age_hours: Any) -> Optional[float]:
    """TLE epoch age in hours -> staleness threat [0..100].

    0h (fresh) -> 0 (no threat). >=48h -> 100 (data confidence collapsed).
    Negative ages (clock skew) clamp to 0.
    """
    v = _to_float(age_hours)
    if v is None:
        return None
    v_clamped = _clamp(v, 0.0, TLE_AGE_HOURS_MAX)
    return v_clamped / TLE_AGE_HOURS_MAX * 100.0


_NORMALIZERS = {
    "kp": normalize_kp,
    "xray": normalize_xray,
    "seismic": normalize_seismic,
    "air": normalize_air,
    "tle_age": normalize_tle_age,
}


def compute_threat_index(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the Global Threat Index from raw component values.

    Args:
        raw: dict with keys (any subset; absent or None = unavailable):
            kp              float, NOAA planetary K-index [0..9]
            xray_wm2        float, GOES X-Ray long-band flux W/m^2
            seismic_score   float, USGS aggregate [0..100]
            air_density_pct float, OpenSky density [0..100]
            tle_age_hours   float, hours since ISS TLE epoch

    Returns:
        {
          "index": float|None,            # 0..100, None if all components missing
          "state": "live"|"degraded"|"unavailable",
          "missing": [str],               # component names that were unavailable
          "components": {
            name: {
              "raw": value,
              "normalized": float|None,
              "available": bool,
              "weight_nominal": float,
              "weight_effective": float,
            }
          },
          "weights_sum_effective": float, # sum of nominal weights for available components
        }
    """
    components: Dict[str, Dict[str, Any]] = {}
    weights_available_sum = 0.0
    weighted_sum = 0.0
    missing: List[str] = []

    for name, weight in WEIGHTS_NOMINAL.items():
        raw_key = _RAW_KEYS[name]
        raw_value = raw.get(raw_key)
        normalized = _NORMALIZERS[name](raw_value)
        available = normalized is not None
        if available:
            weights_available_sum += weight
            weighted_sum += weight * normalized
        else:
            missing.append(name)
        components[name] = {
            "raw": raw_value,
            "normalized": normalized,
            "available": available,
            "weight_nominal": weight,
            "weight_effective": 0.0,
        }

    if weights_available_sum > 0:
        index_value = weighted_sum / weights_available_sum
        for name, comp in components.items():
            if comp["available"]:
                comp["weight_effective"] = comp["weight_nominal"] / weights_available_sum
        state = "live" if not missing else "degraded"
        index_out: Optional[float] = round(index_value, 2)
    else:
        index_out = None
        state = "unavailable"

    return {
        "index": index_out,
        "state": state,
        "missing": missing,
        "components": components,
        "weights_sum_effective": round(weights_available_sum, 4),
    }
