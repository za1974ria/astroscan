def apod_fr_json_impl(
    jsonify,
    log,
):
    """APOD NASA : titre + explication en FR (cache JSON + Claude).

    PASS 27.14 (2026-05-09) — Cascade graceful (latence 3-10s → ~50ms cas nominal) :
      S1. cache disque entrée DU JOUR avec title_fr valide → retour immédiat
      S2. cache négatif actif (NASA récemment fail) → retour entrée la plus récente (stale OK)
      S3. fetch NASA timeout réduit 4s + Claude API si nouvelle entrée
      S4. cache disque stale (entrée la plus récente, hier ou avant) en dernier recours
    """
    try:
        from apod_translator import (
            build_or_refresh_current_apod,
            fetch_apod,
            get_latest_cached_entry,
            get_today_cached_entry,
            is_negative_cache_active,
            load_cache,
            mark_negative_cache,
        )

        # === S1 : cache disque entrée du jour avec title_fr valide ===
        today_entry = get_today_cached_entry()
        if today_entry:
            pub = dict(today_entry)
            pub.pop("translation_warn", None)
            pub["meta"] = {
                "source": "apod_cache",
                "status": "cache_hit",
                "last_updated": pub.get("date") or "",
            }
            return jsonify(pub)

        # === S2 : cache négatif actif → entrée la plus récente (stale OK) ===
        if is_negative_cache_active():
            stale = get_latest_cached_entry()
            if stale:
                out = dict(stale)
                out.pop("translation_warn", None)
                out["from_cache_only"] = True
                out["warn"] = "NASA récemment indisponible (cache négatif 5 min actif)"
                out["meta"] = {
                    "source": "apod_cache",
                    "status": "stale_cache_negative",
                    "last_updated": stale.get("date") or "",
                }
                return jsonify(out)
            log.warning("apod_fr_json: negative cache active and no stale entry")
            return jsonify({
                "error": "APOD temporairement indisponible",
                "details": "negative cache active",
            }), 503

        # === S3 : fetch NASA (timeout 4s) ===
        try:
            apod_meta = fetch_apod()
        except Exception as nasa_err:
            mark_negative_cache()
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
    """Page HTML : APOD du jour en français.

    PASS 27.14 (2026-05-09) — Cascade graceful identique à apod_fr_json_impl
    (S1 cache disque jour → S2 cache négatif → S3 NASA timeout 4s → S4 stale)."""
    try:
        from apod_translator import (
            build_or_refresh_current_apod,
            fetch_apod,
            get_latest_cached_entry,
            get_today_cached_entry,
            is_negative_cache_active,
            load_cache,
            mark_negative_cache,
        )

        # === S1 : cache disque entrée du jour avec title_fr valide ===
        today_entry = get_today_cached_entry()
        if today_entry:
            return render_template(
                "apod.html",
                apod=today_entry,
                title="APOD",
                meta={
                    "source": "apod_cache",
                    "status": "cache_hit",
                    "last_updated": today_entry.get("date") or "",
                },
            )

        # === S2 : cache négatif actif → entrée la plus récente (stale OK) ===
        if is_negative_cache_active():
            stale = get_latest_cached_entry()
            if stale:
                return render_template(
                    "apod.html",
                    apod=stale,
                    title="APOD",
                    meta={
                        "source": "apod_cache",
                        "status": "stale_cache_negative",
                        "last_updated": stale.get("date") or "",
                    },
                )
            return (
                render_template("module_not_ready.html", module="APOD (FR)"),
                503,
            )

        # === S3 : fetch NASA (timeout 4s) ===
        try:
            apod_meta = fetch_apod()
        except Exception:
            mark_negative_cache()
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
