def apod_fr_json_impl(
    jsonify,
    log,
):
    """APOD NASA : titre + explication en FR (cache JSON + Claude)."""
    try:
        from apod_translator import (
            build_or_refresh_current_apod,
            fetch_apod,
            get_latest_cached_entry,
            load_cache,
        )

        try:
            apod_meta = fetch_apod()
        except Exception as nasa_err:
            stale = get_latest_cached_entry()
            if stale:
                out = dict(stale)
                out.pop("translation_warn", None)
                out["from_cache_only"] = True
                out["warn"] = str(nasa_err)[:240]
                out["meta"] = {
                    "source": "apod_cache",
                    "status": "stale_cache",
                    "last_updated": stale.get("date") or "",
                }
                return jsonify(out)
            # No stale cache — return 503 (service temporarily unavailable).
            # Avoids the outer except re-mapping this to 502 Bad Gateway.
            log.warning("apod_fr_json: NASA unreachable, no cache available: %s", nasa_err)
            return jsonify({
                "error": "APOD temporairement indisponible",
                "details": str(nasa_err)[:240],
            }), 503
        day = (apod_meta.get("date") or "").strip()
        cache = load_cache()
        if (
            day
            and cache.get(day, {}).get("title_fr")
            and not cache[day].get("translation_failed")
        ):
            pub = dict(cache[day])
            pub.pop("translation_warn", None)
            pub["meta"] = {
                "source": "apod_cache",
                "status": "cache_hit",
                "last_updated": pub.get("date") or day,
            }
            return jsonify(pub)
        entry = build_or_refresh_current_apod(apod_meta)
        pub = dict(entry)
        pub.pop("translation_warn", None)
        pub["meta"] = {
            "source": "nasa_apod",
            "status": "ok",
            "last_updated": pub.get("date") or day,
        }
        return jsonify(pub)
    except RuntimeError as e:
        log.warning("apod_fr_json: %s", e)
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        log.warning("apod_fr_json: %s", e)
        return jsonify({"error": str(e)}), 502


def apod_fr_view_impl(
    render_template,
    log,
):
    """Page HTML : APOD du jour en français."""
    try:
        from apod_translator import (
            build_or_refresh_current_apod,
            fetch_apod,
            get_latest_cached_entry,
            load_cache,
        )

        try:
            apod_meta = fetch_apod()
        except Exception:
            stale = get_latest_cached_entry()
            if stale:
                return render_template(
                    "apod.html",
                    apod=stale,
                    title="APOD",
                    meta={
                        "source": "apod_cache",
                        "status": "stale_cache",
                        "last_updated": stale.get("date") or "",
                    },
                )
            raise
        day = (apod_meta.get("date") or "").strip()
        cache = load_cache()
        if (
            day
            and cache.get(day, {}).get("title_fr")
            and not cache[day].get("translation_failed")
        ):
            return render_template(
                "apod.html",
                apod=cache[day],
                title="APOD",
                meta={
                    "source": "apod_cache",
                    "status": "cache_hit",
                    "last_updated": cache[day].get("date") or day,
                },
            )
        entry = build_or_refresh_current_apod(apod_meta)
        return render_template(
            "apod.html",
            apod=entry,
            title="APOD",
            meta={
                "source": "nasa_apod",
                "status": "ok",
                "last_updated": entry.get("date") or day,
            },
        )
    except RuntimeError:
        return (
            render_template("module_not_ready.html", module="APOD (FR)"),
            503,
        )
    except Exception as e:
        log.warning("apod_fr_view: %s", e)
        return (
            render_template("module_not_ready.html", module="APOD (FR)"),
            502,
        )
