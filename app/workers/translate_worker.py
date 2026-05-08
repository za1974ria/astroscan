"""PASS 21.1 (2026-05-08) — Worker de traduction des observations.

Extrait depuis station_web.py:4095-4143 lors de PASS 21.1.

Daemon worker qui boucle toutes les 10 minutes pour :
1. Sélectionner jusqu'à 5 observations dont ``rapport_fr`` est vide mais
   ``analyse_gemini`` est rempli
2. Demander à Gemini un résumé en français (2 phrases) via
   ``app.services.ai_translate._call_gemini``
3. Mettre à jour la colonne ``rapport_fr`` en base

Démarré depuis ``app/bootstrap.py:60`` via le shim ``from station_web
import translate_worker``. Doit rester rétro-compatible : son ``__name__``
et sa signature ne doivent pas changer.

Dépendances inverses :
- ``DB_PATH`` (chemin SQLite) — défini dans station_web et lazy-importé
  ici à l'intérieur de la fonction (au moment du premier tour de boucle)
- ``log`` (logger Python) — idem
"""
from __future__ import annotations

import sqlite3
import time


def translate_worker() -> None:
    """
    Daemon worker:
    - every 10 minutes, translate/summarize up to 5 observations with empty rapport_fr
    - never runs in Flask request context
    """
    # Lazy imports inside la boucle — évite le cycle station_web ↔
    # app.workers.translate_worker au load. Au moment du premier tour,
    # station_web est entièrement chargé (le worker est démarré
    # post-bootstrap).
    from station_web import DB_PATH, log
    # PASS 19 : _call_gemini extrait → app/services/ai_translate.py
    from app.services.ai_translate import _call_gemini

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT id, analyse_gemini FROM observations "
                "WHERE COALESCE(TRIM(rapport_fr), '') = '' "
                "AND COALESCE(TRIM(analyse_gemini), '') <> '' "
                "LIMIT 5"
            ).fetchall()

            for row in rows:
                obs_id = row["id"]
                src = (row["analyse_gemini"] or "").strip()
                if not src:
                    continue
                prompt = (
                    "Résume en 2 phrases en français pour l'observatoire "
                    "ORBITAL-CHOHRA à Tlemcen : " + row["analyse_gemini"][:500]
                )
                reply, err = _call_gemini(prompt)
                if reply and len(str(reply).strip()) > 0:
                    try:
                        cur.execute(
                            "UPDATE observations SET rapport_fr=? WHERE id=?",
                            (str(reply).strip(), obs_id),
                        )
                        conn.commit()
                    except Exception as e_upd:
                        log.warning("translate_worker update id=%s: %s", obs_id, e_upd)
            conn.close()
        except Exception as e:
            log.warning("translate_worker: %s", e)
        try:
            time.sleep(600)
        except Exception:
            time.sleep(60)


__all__ = ["translate_worker"]
