def api_sdr_passes_impl(
    jsonify,
    STATION,
    Path,
    json_module,
    time_module,
    subprocess_module,
    log,
):
    """Prochains passages NOAA-15/18/19 pour Tlemcen via Skyfield SGP4 (données réelles).

    PASS 27.5 (2026-05-09) — Graceful degradation 12 s → <500 ms :
    cascade source primaire (TLE_CACHE worker en mémoire, ~370-1000 sats déjà
    hydratés par tle_refresh_loop) → cache local noaa_tle.json (TTL 2 h, avec
    cache négatif failed_at 5 min) → CelesTrak en dernier recours (timeout
    réduit 5 s + écriture failed_at si fail). Si toutes les sources échouent,
    retour graceful avec degraded=True (sans planter le frontend).
    """
    from skyfield.api import load, EarthSatellite, wgs84

    _lat, _lon, _alt_m = 34.87, 1.32, 800.0
    _min_el = 5.0
    noaa_norad = {
        "NOAA-15": {"norad": 25338, "freq": "137.620 MHz"},
        "NOAA-18": {"norad": 28654, "freq": "137.9125 MHz"},
        "NOAA-19": {"norad": 33591, "freq": "137.100 MHz"},
    }
    target_norads = {info["norad"] for info in noaa_norad.values()}
    tles_raw = {}

    # === STRATÉGIE 1 : TLE_CACHE worker principal (in-memory, ~0 ms) ===
    try:
        from app.workers.tle_worker import TLE_CACHE
        items = TLE_CACHE.get("items", []) if isinstance(TLE_CACHE, dict) else []
        for item in items:
            norad = (
                item.get("norad_id")
                or item.get("catnr")
                or item.get("NORAD_CAT_ID")
                or item.get("norad_cat_id")
            )
            if norad is None:
                continue
            try:
                norad_int = int(norad)
            except (TypeError, ValueError):
                continue
            if norad_int in target_norads:
                tles_raw[norad_int] = {
                    "name": (
                        item.get("name")
                        or item.get("OBJECT_NAME")
                        or f"NORAD {norad_int}"
                    ),
                    "tle1": item.get("tle1") or item.get("TLE_LINE1") or item.get("tle_line1"),
                    "tle2": item.get("tle2") or item.get("TLE_LINE2") or item.get("tle_line2"),
                }
        if tles_raw:
            log.info(f"sdr/passes: TLE NOAA depuis worker cache ({len(tles_raw)}/3)")
    except Exception as e:
        log.warning(f"sdr/passes: TLE worker cache unavailable: {e}")

    # === STRATÉGIE 2 : fichier cache local data/noaa_tle.json ===
    noaa_cache_path = Path(f"{STATION}/data/noaa_tle.json")
    if len(tles_raw) < 3:
        try:
            if noaa_cache_path.exists():
                with open(noaa_cache_path) as f:
                    cached = json_module.load(f)
                # CACHE NÉGATIF : si fetch a foiré récemment, ne pas retry
                failed_at = cached.get("failed_at", 0)
                if failed_at and (time_module.time() - failed_at) < 300:
                    log.info("sdr/passes: cache négatif actif (Celestrak récent fail), skip fetch")
                # Cache positif valide < 2 h
                elif time_module.time() - cached.get("timestamp", 0) < 7200:
                    file_tles = {int(k): v for k, v in (cached.get("tles") or {}).items()}
                    for norad, tle in file_tles.items():
                        if norad in target_norads and norad not in tles_raw:
                            tles_raw[norad] = tle
        except Exception as e:
            log.warning(f"sdr/passes: cache file read error: {e}")

    # === STRATÉGIE 3 : fetch CelesTrak (dernier recours, timeout réduit 5 s) ===
    if len(tles_raw) < 3:
        # Vérifier le cache négatif AVANT fetch
        skip_fetch = False
        if noaa_cache_path.exists():
            try:
                with open(noaa_cache_path) as f:
                    cached_check = json_module.load(f)
                failed_at = cached_check.get("failed_at", 0)
                if failed_at and (time_module.time() - failed_at) < 300:
                    skip_fetch = True
            except Exception:
                pass

        if not skip_fetch:
            fetched_ok = False
            try:
                r = subprocess_module.run(
                    [
                        "curl", "-s", "--ipv4", "--max-time", "5",
                        "-A", "ORBITAL-CHOHRA/1.0",
                        "https://celestrak.org/NORAD/elements/gp.php?GROUP=noaa&FORMAT=tle",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=6,
                )
                raw = r.stdout.strip()
                if raw and "1 " in raw:
                    lines = [l.strip() for l in raw.splitlines() if l.strip()]
                    i = 0
                    while i + 2 < len(lines):
                        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
                            try:
                                nid = int(lines[i + 1][2:7].strip())
                                tles_raw[nid] = {
                                    "name": lines[i],
                                    "tle1": lines[i + 1],
                                    "tle2": lines[i + 2],
                                }
                            except ValueError:
                                pass
                            i += 3
                        else:
                            i += 1
                    # Cache positif
                    try:
                        noaa_cache_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(noaa_cache_path, "w") as f:
                            json_module.dump(
                                {
                                    "timestamp": time_module.time(),
                                    "tles": {str(k): v for k, v in tles_raw.items()},
                                },
                                f,
                            )
                        fetched_ok = True
                        log.info(f"sdr/passes: TLE NOAA rechargés depuis CelesTrak ({len(tles_raw)} sats)")
                    except Exception as e:
                        log.warning(f"sdr/passes: cache write: {e}")
            except Exception as e:
                log.warning(f"sdr/passes: Celestrak fetch failed: {e}")

            # Cache négatif si pas réussi
            if not fetched_ok:
                try:
                    noaa_cache_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(noaa_cache_path, "w") as f:
                        json_module.dump({
                            "failed_at": time_module.time(),
                            "tles": {},
                        }, f)
                except Exception:
                    pass

    # === GRACEFUL DEGRADATION : si toujours rien, retour rapide ===
    if not tles_raw:
        log.warning("sdr/passes: aucune TLE NOAA disponible, retour dégradé")
        return jsonify({
            "ok": True,
            "passes": [],
            "station": "Tlemcen, Algérie",
            "count": 0,
            "method": "skyfield_sgp4",
            "degraded": True,
            "reason": "TLE NOAA temporairement indisponibles (Celestrak/AMSAT)",
        })

    # ── Calcul SGP4 via Skyfield ─────────────────────────────────────────────
    ts = load.timescale()
    observer = wgs84.latlon(_lat, _lon, elevation_m=_alt_m)
    t0 = ts.now()
    t1 = ts.tt_jd(t0.tt + 2.0)  # 48 heures

    out = []
    for sat_name, info in noaa_norad.items():
        tle_data = tles_raw.get(info["norad"])
        if not tle_data:
            log.warning(f'sdr/passes: TLE manquant {sat_name} (NORAD {info["norad"]})')
            continue
        try:
            sat = EarthSatellite(tle_data["tle1"], tle_data["tle2"], tle_data.get("name", sat_name), ts)
            t_events, events = sat.find_events(observer, t0, t1, altitude_degrees=_min_el)
            i = 0
            while i + 2 < len(events):
                if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
                    aos_t, max_t, los_t = t_events[i], t_events[i + 1], t_events[i + 2]
                    alt, _az, _d = (sat - observer).at(max_t).altaz()
                    out.append(
                        {
                            "sat": sat_name,
                            "freq": info["freq"],
                            "aos": int(aos_t.utc_datetime().timestamp()),
                            "los": int(los_t.utc_datetime().timestamp()),
                            "max_el": round(alt.degrees, 1),
                            "simulated": False,
                        }
                    )
                    i += 3
                else:
                    i += 1
        except Exception as e:
            log.warning(f"sdr/passes: Skyfield SGP4 {sat_name}: {e}")

    out.sort(key=lambda x: x["aos"])
    return jsonify({"ok": True, "passes": out[:12], "station": "Tlemcen, Algérie", "count": len(out), "method": "skyfield_sgp4"})
