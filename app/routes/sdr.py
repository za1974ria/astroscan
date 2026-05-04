def api_sdr_passes_impl(
    jsonify,
    STATION,
    Path,
    json_module,
    time_module,
    subprocess_module,
    log,
):
    """Prochains passages NOAA-15/18/19 pour Tlemcen via Skyfield SGP4 (données réelles)."""
    from skyfield.api import load, EarthSatellite, wgs84

    _lat, _lon, _alt_m = 34.87, 1.32, 800.0
    _min_el = 5.0
    noaa_norad = {
        "NOAA-15": {"norad": 25338, "freq": "137.620 MHz"},
        "NOAA-18": {"norad": 28654, "freq": "137.9125 MHz"},
        "NOAA-19": {"norad": 33591, "freq": "137.100 MHz"},
    }

    # ── 1. Charger les TLE NOAA (cache 2h → CelesTrak → cache principal) ──
    noaa_cache_path = Path(f"{STATION}/data/noaa_tle.json")
    tles_raw = {}
    try:
        if noaa_cache_path.exists():
            with open(noaa_cache_path) as f:
                cached = json_module.load(f)
            if time_module.time() - cached.get("timestamp", 0) < 7200:
                tles_raw = {int(k): v for k, v in cached.get("tles", {}).items()}
    except Exception:
        pass

    if not tles_raw:
        # Fetch via curl (urllib bloqué Hetzner pour CelesTrak)
        try:
            r = subprocess_module.run(
                [
                    "curl",
                    "-s",
                    "--ipv4",
                    "--max-time",
                    "12",
                    "-A",
                    "ORBITAL-CHOHRA/1.0",
                    "https://celestrak.org/NORAD/elements/gp.php?GROUP=noaa&FORMAT=tle",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            raw = r.stdout.strip()
            if raw and "1 " in raw:
                lines = [l.strip() for l in raw.splitlines() if l.strip()]
                i = 0
                while i + 2 < len(lines):
                    if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
                        try:
                            norad_id = int(lines[i + 1][2:7].strip())
                            tles_raw[norad_id] = {
                                "name": lines[i],
                                "tle1": lines[i + 1],
                                "tle2": lines[i + 2],
                            }
                        except ValueError:
                            pass
                        i += 3
                    else:
                        i += 1
                if tles_raw:
                    noaa_cache_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(noaa_cache_path, "w") as f:
                        json_module.dump(
                            {
                                "timestamp": time_module.time(),
                                "tles": {str(k): v for k, v in tles_raw.items()},
                            },
                            f,
                        )
                    log.info(f"sdr/passes: TLE NOAA rechargés depuis CelesTrak ({len(tles_raw)} sats)")
        except Exception as e:
            log.warning(f"sdr/passes: CelesTrak fetch: {e}")

    # Fallback: chercher par NORAD dans le cache principal active.tle
    norad_needed = {info["norad"] for info in noaa_norad.values()} - set(tles_raw)
    if norad_needed:
        try:
            active_tle = Path(f"{STATION}/data/tle/active.tle")
            if active_tle.exists():
                with open(active_tle) as f:
                    lines = [l.strip() for l in f if l.strip()]
                i = 0
                while i + 2 < len(lines) and norad_needed:
                    if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
                        try:
                            nid = int(lines[i + 1][2:7].strip())
                            if nid in norad_needed:
                                tles_raw[nid] = {"name": lines[i], "tle1": lines[i + 1], "tle2": lines[i + 2]}
                                norad_needed.discard(nid)
                        except ValueError:
                            pass
                        i += 3
                    else:
                        i += 1
        except Exception as e:
            log.warning(f"sdr/passes: active.tle fallback: {e}")

    # ── 2. Calcul SGP4 via Skyfield ──────────────────────────────────────────
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
