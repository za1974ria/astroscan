#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module ce_soir_module
Retourne des données structurées pour la page /ce_soir.
Ici on fournit un jeu de données statique mais déjà formaté
comme attendu par le JavaScript de ce_soir.html.
"""
from datetime import datetime, timezone


def get_tonight_data():
    """Retourne un dict avec: moon_phase, summary, dso, planets."""

    # Lune (valeurs d'exemple)
    moon_phase = {
        "icon": "🌖",
        "name": "Lune gibbeuse décroissante",
        "illumination": 68,
        "good_for_obs": False,
    }

    # Résumé (valeurs d'exemple)
    summary = {
        "visible_dso": 18,
        "visible_planets": 4,
        "best_object": {
            "id": "M42",
            "name": "Nébuleuse d'Orion",
            "alt": 45,
            "direction": "S‑SE",
        },
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
    }

    # Quelques objets du ciel profond (exemple)
    dso = [
        {
            "id": "M42",
            "name": "Nébuleuse d'Orion",
            "type": "nebula",
            "mag": 4.0,
            "alt": 45,
            "direction": "S‑SE",
            "visibility": {"stars": 4, "color": "#00ff88"},
        },
        {
            "id": "M31",
            "name": "Galaxie d'Andromède",
            "type": "galaxy",
            "mag": 3.4,
            "alt": 30,
            "direction": "NO",
            "visibility": {"stars": 3, "color": "#00d4ff"},
        },
        {
            "id": "M13",
            "name": "Amas d'Hercule",
            "type": "cluster",
            "mag": 5.8,
            "alt": 55,
            "direction": "NE",
            "visibility": {"stars": 4, "color": "#ffaa00"},
        },
    ]

    # Planètes (exemple)
    planets = [
        {
            "name": "Jupiter",
            "icon": "♃",
            "alt": 35,
            "direction": "SE",
            "color": "#ffaa00",
            "visibility": {"label": "EXCELLENTE", "color": "#00ff88"},
            "source": "Éphémérides locales",
        },
        {
            "name": "Saturne",
            "icon": "♄",
            "alt": 20,
            "direction": "S",
            "color": "#e4d191",
            "visibility": {"label": "BONNE", "color": "#00d4ff"},
            "source": "Éphémérides locales",
        },
        {
            "name": "Mars",
            "icon": "♂",
            "alt": 15,
            "direction": "E",
            "color": "#ff6644",
            "visibility": {"label": "MOYENNE", "color": "#ffaa00"},
            "source": "Éphémérides locales",
        },
    ]

    return {
        "moon_phase": moon_phase,
        "summary": summary,
        "dso": dso,
        "planets": planets,
    }

