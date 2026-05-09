from app.services.cache import cache_read, cache_write
from app.services.tle import get_iss_tle_from_sources
from app.services.accuracy import compute_iss_accuracy
from app.services.accuracy_history import push_accuracy_sample, get_accuracy_stats


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
    - Cache 15 s pour limiter les appels externes.
    """
    cache_cleanup()
    system_log("ISS API called")
    cached = cache_read(cache_get, "iss", 15)
    if cached is not None:
        return jsonify(cached)
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
    iss["timestamp"] = int(time_module.time())
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

    if sgp4_data:
        iss["sgp4"] = sgp4_data
        iss["meta"] = {
            "source": "SGP4",
            "status": "live",
            "confidence": "high",
            "last_updated": sgp4_data.get("timestamp"),
        }
        _emit_diag_json(
            {
                "event": "iss_sgp4_success",
                "reason": sgp4_reason,
            }
        )
    else:
        iss["meta"] = {
            "source": "fallback",
            "status": "fallback",
            "confidence": "medium",
            "last_updated": datetime_cls.now(timezone_cls.utc).isoformat().replace("+00:00", "Z"),
        }
        _emit_diag_json(
            {
                "event": "iss_sgp4_failed",
                "reason": sgp4_reason,
            }
        )
    cache_write(cache_set, "iss", iss)
    return jsonify(iss)
