"""Service db_visitors — connexion SQLite partagée pour les analytics visiteurs.

Extrait depuis station_web.py L5340-L5343 lors de PASS 23.
station_web.py conserve un alias re-export pour la compat des imports legacy.
"""
import sqlite3 as _sqlite3


def _get_db_visitors():
    return _sqlite3.connect("/root/astro_scan/data/archive_stellaire.db")
