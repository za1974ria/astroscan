from app.services.tle import get_iss_tle_from_sources
from app.services.accuracy import compute_iss_accuracy
from app.services.accuracy_history import push_accuracy_sample, get_accuracy_stats


# Anti-mensonge thresholds (axe1 fix 2026-05-29):
#   ≤ _FRESH_S    → status="live"     confidence="high"
#   ≤ _STALE_S    → status="stale"    confidence="medium" + meta.warning
#   > _STALE_S    → status="stale"    confidence="low"    + meta.warning
# Cache Redis bornée à _CACHE_TTL_S pour absorber les requêtes simultanées ;
# de toute façon le payload embarque _cached_at vérifié applicativement, donc
# une éventuelle régression du TTL Redis (cf. /tmp/fix_iss_diag.md : cache_get
# ignore son paramètre ttl) ne rouvre pas la fenêtre "live" au-delà de cette
# durée.
_CACHE_KEY = "iss"
_CACHE_TTL_S = 5
_FRESH_S = 30
_STALE_S = 300


def _parse_tle_epoch_iso(line1):
    """Return ISO string for the TLE epoch encoded in line1, or None."""
    try:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        s = (line1 or "").strip()
        if len(s) < 32:
            return None
        yy = int(s[18:20])
        doy = float(s[20:32])
        year = 2000 + yy if yy < 57 else 1900 + yy
        epoch = _dt(year, 1, 1, tzinfo=_tz.utc) + _td(days=doy - 1.0)
        return epoch.isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def _compute_meta(last_updated_iso, source, tle_epoch_iso, datetime_cls, timezone_cls):
    """Build the meta dict with honest age + status + confidence.

    `last_updated_iso` MUST be the SGP4 propagation timestamp (i.e. the
    instant for which the position is valid). The TLE epoch is exposed
    separately via `tle_epoch_iso` since it is normal for the TLE itself
    to be a few hours old while the propagated position is fresh.

    Anti-mensonge: never returns status="live"/confidence="high" once
    age_seconds exceeds _FRESH_S, regardless of caller context. Fallback
    sources never claim "high" confidence even when fresh.
    """
    now = datetime_cls.now(timezone_cls.utc)
    age_seconds = None
    if last_updated_iso:
        try:
            ts = str(last_updated_iso).replace("Z", "+00:00")
            last_dt = datetime_cls.fromisoformat(ts)
            age_seconds = int((now - last_dt).total_seconds())
        except Exception:
            age_seconds = None

    meta = {
        "source": source,
        "last_updated": last_updated_iso,
        "tle_epoch_iso": tle_epoch_iso,
        "age_seconds": age_seconds,
        "thresholds_s": {"fresh": _FRESH_S, "stale": _STALE_S},
    }

    if source != "SGP4":
        meta["status"] = "fallback"
        meta["confidence"] = "medium"
        if age_seconds is None:
            meta["confidence"] = "low"
            meta["warning"] = "Fallback position with unknown timestamp"
        elif age_seconds > _STALE_S:
            meta["confidence"] = "low"
            meta["warning"] = (
                "Fallback position outdated "
                f"(age={age_seconds}s > {_STALE_S}s)"
            )
        return meta

    if age_seconds is None:
        meta["status"] = "stale"
        meta["confidence"] = "low"
        meta["warning"] = "ISS propagation timestamp missing"
    elif age_seconds > _STALE_S:
        meta["status"] = "stale"
        meta["confidence"] = "low"
        meta["warning"] = (
            "ISS position outdated — SGP4 propagation has not been refreshed "
            f"(age={age_seconds}s > {_STALE_S}s)"
        )
    elif age_seconds > _FRESH_S:
        meta["status"] = "stale"
        meta["confidence"] = "medium"
        meta["warning"] = f"ISS position is {age_seconds}s old"
    else:
        meta["status"] = "live"
        meta["confidence"] = "high"
    return meta


def _position_is_invalid(lat, lon):
    """Return True when the ground-track position must NOT be presented as live.

    Triggered by:
      - lat/lon non-numeric or None;
      - Null Island sentinel (lat == 0 AND lon == 0) — the fallback dict
        seeds these zeros when ``_fetch_iss_live`` returns nothing, so a
        (0,0) ground point is treated as "data absent" rather than a real
        equatorial fix. ISS does cross the equator near (0,0) twice per
        orbit, but at 7.66 km/s the probability of catching it exactly on
        the prime meridian with both coords at zero to floating-point
        precision is effectively nil — the (0,0) signature is a sentinel,
        not a measurement.
    """
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return True
    try:
        if lat != lat or lon != lon:  # NaN
            return True
    except Exception:
        return True
    if lat == 0 and lon == 0:
        return True
    return False


def _force_unavailable_meta(meta, source_hint=None):
    """Stamp the meta dict so a (0,0) / missing ground-track can never be
    presented as live or even partly-trusted. Preserves age_seconds for
    observability but caps status/confidence at unavailable/none.

    Used both on cache-miss recompute and on cache-hit re-derivation, so a
    payload that was once invalid cannot resurrect as ``live`` on the next
    request by virtue of a fresh ``last_updated``.
    """
    meta = dict(meta or {})
    if source_hint:
        meta.setdefault("source", source_hint)
    meta["status"] = "unavailable"
    meta["confidence"] = "none"
    meta["warning"] = (
        "ISS position unavailable — live fetch and SGP4 ground-track both "
        "missing (lat/lon are sentinel zeros or non-numeric)"
    )
    return meta


def api_iss_impl(
    cache_cleanup,
    system_log,
    cache_get,
    jsonify,
    _cached,
    _fetch_iss_live,
    _get_iss_crew,
    cache_set,
    time_module,
    propagate_tle_debug,
    datetime_cls,
    timezone_cls,
    TLE_CACHE,
    TLE_ACTIVE_PATH,
    _parse_tle_file,
    _emit_diag_json,
    os_module,
):
    """
    Endpoint canonique ISS :
    - Position + altitude + vitesse via whereTheISS / open-notify
    - Nombre d'équipage via open-notify /astros.json
    - Cache 5 s applicatif (anti-mensonge sur la fraîcheur SGP4).
    """
    cache_cleanup()
    system_log("ISS API called")

    now_ts = time_module.time()

    # ── Cache hit (≤ _CACHE_TTL_S, vérifié applicativement via _cached_at) ──
    # On NE fait PAS confiance au TTL côté cache_get : il est ignoré par le
    # backend Redis (cf. services/cache_service.py:102-110). L'horodatage
    # applicatif _cached_at est la seule source de vérité pour la fraîcheur.
    try:
        cached = cache_get(_CACHE_KEY, _CACHE_TTL_S)
    except Exception:
        cached = None
    if isinstance(cached, dict):
        cached_ts = cached.get("_cached_at")
        if isinstance(cached_ts, (int, float)) and (now_ts - cached_ts) <= _CACHE_TTL_S:
            # Re-derive meta with the CURRENT clock so age_seconds reflects
            # serve-time, not cache-write-time. The cache hit is at most
            # _CACHE_TTL_S old, so the SGP4 propagation underneath is always
            # within the "live" window — but we recompute honestly anyway.
            prev_meta = cached.get("meta") or {}
            new_meta = _compute_meta(
                prev_meta.get("last_updated"),
                prev_meta.get("source", "SGP4"),
                prev_meta.get("tle_epoch_iso"),
                datetime_cls, timezone_cls,
            )
            # Anti-mensonge Null-Island : si lat/lon stockés sont (0,0) ou
            # non numériques, refuser de re-marquer "live" même sur cache hit.
            if _position_is_invalid(cached.get("lat"), cached.get("lon")):
                new_meta = _force_unavailable_meta(new_meta, source_hint=prev_meta.get("source"))
            cached["meta"] = new_meta
            return jsonify(cached)

    # ── Cache miss → fetch live + propagate SGP4 ─────────────────────────
    iss = _cached("iss_live", 5, _fetch_iss_live)
    if not iss:
        iss = {
            "ok": False,
            "lat": 0.0,
            "lon": 0.0,
            "alt": 408.0,
            "speed": 27600.0,
            "region": "Inconnu",
        }
    crew = _get_iss_crew()
    iss["crew"] = crew
    iss["timestamp"] = int(now_ts)
    accuracy = compute_iss_accuracy(iss.get("lat", 0.0), iss.get("lon", 0.0))
    iss["accuracy"] = accuracy
    if accuracy.get("distance_km") is not None:
        push_accuracy_sample(accuracy["distance_km"])
    iss["accuracy_stats"] = get_accuracy_stats()

    tle1, tle2 = get_iss_tle_from_sources(
        TLE_CACHE=TLE_CACHE,
        TLE_ACTIVE_PATH=TLE_ACTIVE_PATH,
        _parse_tle_file=_parse_tle_file,
        _emit_diag_json=_emit_diag_json,
        os_module=os_module,
    )
    _emit_diag_json(
        {
            "event": "iss_sgp4_attempt",
            "has_tle1": bool(tle1),
            "has_tle2": bool(tle2),
        }
    )
    sgp4_data = None
    sgp4_reason = "missing_tle"
    if tle1 and tle2:
        sgp4_data, sgp4_reason = propagate_tle_debug(tle1, tle2)

    tle_epoch_iso = _parse_tle_epoch_iso(tle1)

    if sgp4_data:
        iss["sgp4"] = sgp4_data
        iss["meta"] = _compute_meta(
            sgp4_data.get("timestamp"),
            "SGP4",
            tle_epoch_iso,
            datetime_cls, timezone_cls,
        )
        _emit_diag_json(
            {
                "event": "iss_sgp4_success",
                "reason": sgp4_reason,
            }
        )
    else:
        # Fallback path: position came from _fetch_iss_live (or zeros).
        # Last_updated is now() since whereTheISS / open-notify deliver
        # near-real-time snapshots; the source label switches to "fallback"
        # so _compute_meta caps confidence at medium regardless of age.
        last_updated = datetime_cls.now(timezone_cls.utc).isoformat().replace("+00:00", "Z")
        iss["meta"] = _compute_meta(
            last_updated, "fallback", tle_epoch_iso,
            datetime_cls, timezone_cls,
        )
        _emit_diag_json(
            {
                "event": "iss_sgp4_failed",
                "reason": sgp4_reason,
            }
        )

    # ── Anti-mensonge Null-Island ────────────────────────────────────────
    # Si la position de surface est invalide ((0,0) sentinelle, None, NaN,
    # non-numérique), le meta NE PEUT PAS rester en "live"/"high" même si
    # SGP4 a réussi : c'est la position de surface qui est consommée par
    # les clients (carte, dashboard) et un point Null-Island dégradé en
    # "live" est un mensonge cosmétique. Le champ `_position_invalid` est
    # ajouté pour traçabilité.
    if _position_is_invalid(iss.get("lat"), iss.get("lon")):
        iss["meta"] = _force_unavailable_meta(iss["meta"], source_hint=iss["meta"].get("source"))
        iss["_position_invalid"] = True
        _emit_diag_json(
            {
                "event": "iss_position_invalid",
                "lat": iss.get("lat"),
                "lon": iss.get("lon"),
                "sgp4_success": bool(sgp4_data),
            }
        )

    # ── Stash applicative timestamp + write with real TTL ────────────────
    # cache_set(key, value, ttl) propage le TTL à Redis ; on aligne le TTL
    # Redis et la fenêtre applicative _CACHE_TTL_S pour éviter qu'une vieille
    # entrée traîne plus longtemps que prévu.
    iss["_cached_at"] = now_ts
    try:
        cache_set(_CACHE_KEY, iss, _CACHE_TTL_S)
    except TypeError:
        # Shim signature compat (key, value only) — best-effort fallback.
        cache_set(_CACHE_KEY, iss)

    return jsonify(iss)
