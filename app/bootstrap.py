"""Module bootstrap — démarre les threads de fond app-level.
Migré depuis station_web.py top-level lors de PASS 25.1.
Garde-fou anti-double-start : _BOOTSTRAP_DONE assure 1 run par processus.
"""
import logging

log = logging.getLogger(__name__)
_BOOTSTRAP_DONE = False


def start_background_threads():
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        log.info("[Bootstrap] threads already started, skipping")
        return
    _BOOTSTRAP_DONE = True

    import threading as _t

    # Thread 1: tle_refresh_loop (ex station_web.py L1614-L1624)
    try:
        from station_web import (
            load_tle_cache_from_disk,
            fetch_tle_from_celestrak,
            tle_refresh_loop,
        )
        try:
            load_tle_cache_from_disk()
        except Exception as e:
            log.warning("[Bootstrap] load_tle_cache_from_disk failed: %s", e)
        try:
            fetch_tle_from_celestrak()
        except Exception:
            pass
        _t.Thread(
            target=tle_refresh_loop, daemon=True, name="tle_refresh_loop"
        ).start()
        log.info("[Bootstrap] thread tle_refresh_loop started")
    except Exception as e:
        log.error("[Bootstrap] thread tle_refresh_loop failed: %s", e)

    # Thread 2: lab_image_collector (ex station_web.py L4910)
    try:
        from station_web import _start_lab_image_collector
        _start_lab_image_collector()
        log.info("[Bootstrap] thread lab_image_collector started")
    except Exception as e:
        log.error("[Bootstrap] thread lab_image_collector failed: %s", e)

    # Thread 3: skyview_sync (ex station_web.py L4911)
    try:
        from station_web import _start_skyview_sync
        _start_skyview_sync()
        log.info("[Bootstrap] thread skyview_sync started")
    except Exception as e:
        log.error("[Bootstrap] thread skyview_sync failed: %s", e)

    # Thread 4: translate_worker (ex station_web.py L4912-L4915)
    try:
        from station_web import translate_worker
        _t.Thread(
            target=translate_worker, daemon=True, name="translate_worker"
        ).start()
        log.info("[Bootstrap] thread translate_worker started")
    except Exception as e:
        log.error("[Bootstrap] thread translate_worker failed: %s", e)

    # Thread 5: tle_collector (ex station_web.py L5133)
    try:
        from station_web import _start_tle_collector
        _start_tle_collector()
        log.info("[Bootstrap] thread tle_collector started")
    except Exception as e:
        log.error("[Bootstrap] thread tle_collector failed: %s", e)

    log.info("[Bootstrap] all background threads launched")
