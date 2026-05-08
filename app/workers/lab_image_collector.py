"""PASS 21.4 (2026-05-08) — Lab image collector thread (LAST thread migrated).

Extrait depuis station_web.py:3982-4089 lors de PASS 21.4. Avec ce
PASS, **les 4 threads/workers sont désormais tous dans `app/workers/`**
(translate_worker, tle_collector, skyview_sync, lab_image_collector).
Plus aucun thread résidant dans le monolith station_web.py.

Le collector exécute un cycle quotidien de téléchargement d'images
spatiales (telescope, SkyView, NASA APOD, Hubble, JWST, ESA) avec un
pattern leader/standby basé sur ``fcntl.flock`` :

- ``LOCK_FILE = '/tmp/aegis_collector.lock'`` — exclusion mutuelle
  entre les 4 workers Gunicorn. Seul le premier à acquérir le lock
  exécute le cycle ; les autres se mettent en veille.
- ``LAST_RUN_FILE = '/tmp/aegis_collector.lastrun'`` — timestamp Unix
  de la dernière exécution réussie.
- ``COOLDOWN_SECONDS = 60`` — délai minimum entre deux cycles consécutifs
  même si le lock est libre (anti-rafale).

Architecture du cycle :

  _start_lab_image_collector()
    └─ Thread daemon : sleep 60s puis run_collector_safe(_run_lab_image_collector_once)

  run_collector_safe(fn)
    ├─ acquire_lock (fcntl.LOCK_EX | LOCK_NB)
    │    └─ skip si autre worker détient déjà le lock
    ├─ check cooldown (LAST_RUN_FILE)
    │    └─ skip si <60s depuis dernier run
    ├─ fn()                # _run_lab_image_collector_once
    ├─ mark_run (écrit LAST_RUN_FILE + station_web.COLLECTOR_LAST_RUN)
    └─ release_lock

  _run_lab_image_collector_once()
    ├─ run_telescope_collector(RAW_IMAGES, METADATA_DB)
    ├─ _sync_skyview_to_lab()
    ├─ _download_nasa_apod()
    ├─ _download_hubble_images()
    ├─ _download_jwst_images()
    ├─ _download_esa_images()
    └─ schedule next run via threading.Timer(86400s, run_collector_safe(_run_lab_image_collector_once))

Mutation cross-module ``COLLECTOR_LAST_RUN`` :
La fonction ``_aegis_collector_mark_run`` mute ``station_web.COLLECTOR_LAST_RUN``
(défini ligne 198 du monolith) via ``import station_web as _sw; _sw.X = …``
pour préserver la valeur visible dans le namespace de station_web. Audit a
confirmé qu'aucun consommateur externe ne lit cette variable activement
(seul un fichier `.bak` legacy y faisait référence), mais on garde le
contrat de mutation pour rétro-compat défensive.

Lazy imports inside chaque fonction pour éviter le cycle station_web ↔
worker au load.
"""
from __future__ import annotations

import fcntl
import os
import threading
import time
from datetime import datetime, timezone


# ── Constantes du collector (déplacées depuis station_web.py:3982-3984) ──
LOCK_FILE: str = '/tmp/aegis_collector.lock'
LAST_RUN_FILE: str = '/tmp/aegis_collector.lastrun'
COOLDOWN_SECONDS: int = 60


def _aegis_collector_acquire_lock():
    """Acquiert un lock fcntl exclusif non-bloquant. None si déjà détenu."""
    try:
        lock_file = open(LOCK_FILE, 'a+')
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except Exception:
        return None


def _aegis_collector_release_lock(lock_file):
    """Libère le lock fcntl et ferme le file handle."""
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
    except Exception:
        pass


def _aegis_collector_can_run() -> bool:
    """True si plus de COOLDOWN_SECONDS depuis la dernière run."""
    try:
        if not os.path.exists(LAST_RUN_FILE):
            return True
        with open(LAST_RUN_FILE, 'r') as f:
            last = float(f.read().strip())
        return (time.time() - last) > COOLDOWN_SECONDS
    except Exception:
        return True


def _aegis_collector_mark_run() -> None:
    """Écrit le timestamp courant dans LAST_RUN_FILE et mute station_web.COLLECTOR_LAST_RUN."""
    # Lazy import : mutation cross-module préserve la rétro-compat.
    import station_web as _sw

    try:
        with open(LAST_RUN_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception:
        pass
    _sw.COLLECTOR_LAST_RUN = time.time()


def run_collector_safe(run_func):
    """Wrapper avec lock + cooldown qui exécute run_func de manière sécurisée."""
    from station_web import log

    lock = _aegis_collector_acquire_lock()
    if not lock:
        log.info('[AEGIS] Collector skipped (already running)')
        return
    try:
        if not _aegis_collector_can_run():
            log.info('[AEGIS] Collector skipped (cooldown active)')
            return
        log.info('[AEGIS] Collector START (secured)')
        run_func()
        _aegis_collector_mark_run()
        log.info('[AEGIS] Collector END (secured)')
    except Exception as e:
        log.error('[AEGIS] Collector ERROR: %s', e)
    finally:
        _aegis_collector_release_lock(lock)


def _run_lab_image_collector_once() -> None:
    """Cycle complet : telescope → skyview → APOD/Hubble/JWST/ESA. Auto-rescheduled à +24h."""
    # Lazy imports : services + helpers monolith.
    from app.services.lab_helpers import (
        METADATA_DB,
        RAW_IMAGES,
        _sync_skyview_to_lab,
    )
    from station_web import (
        HEALTH_STATE,
        _download_esa_images,
        _download_hubble_images,
        _download_jwst_images,
        _download_nasa_apod,
        _health_set_error,
        log,
    )

    try:
        HEALTH_STATE["collector_status"]["image_collector"] = "running"
    except Exception:
        pass
    log.info("[LAB COLLECTOR] Starting telescope download")
    try:
        from modules.space_sources import run_telescope_collector
        run_telescope_collector(RAW_IMAGES, METADATA_DB)
    except Exception as e:
        log.warning("run_telescope_collector: %s", e)
        _health_set_error("lab_image_collector", e, "warn")
    log.info("[LAB COLLECTOR] Syncing SkyView to Lab")
    _sync_skyview_to_lab()
    log.info("[LAB COLLECTOR] NASA APOD download")
    _download_nasa_apod()
    _download_hubble_images()
    _download_jwst_images()
    _download_esa_images()
    log.info("[LAB COLLECTOR] Completed cycle")
    try:
        HEALTH_STATE["collector_status"]["image_collector"] = "ok"
        HEALTH_STATE["last_sync"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            HEALTH_STATE["image_count"] = len(os.listdir(RAW_IMAGES))
        except Exception:
            HEALTH_STATE["image_count"] = HEALTH_STATE.get("image_count")
    except Exception:
        pass
    # Auto-reschedule pour la run suivante à +24h.
    t = threading.Timer(
        86400.0,
        run_collector_safe,
        args=(_run_lab_image_collector_once,),
    )
    t.daemon = True
    t.start()


def _start_lab_image_collector() -> None:
    """Démarre le thread daemon : sleep 60s puis run_collector_safe."""
    def _run():
        time.sleep(60)
        run_collector_safe(_run_lab_image_collector_once)
    t = threading.Thread(target=_run, daemon=True)
    t.start()


__all__ = [
    "LOCK_FILE",
    "LAST_RUN_FILE",
    "COOLDOWN_SECONDS",
    "_aegis_collector_acquire_lock",
    "_aegis_collector_release_lock",
    "_aegis_collector_can_run",
    "_aegis_collector_mark_run",
    "run_collector_safe",
    "_run_lab_image_collector_once",
    "_start_lab_image_collector",
]
