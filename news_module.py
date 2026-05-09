#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
news_module
Renvoie une petite liste d’actualités spatiales formatées
pour la page /ce_soir (panneau ACTUALITÉS).

Pour un premier déploiement on utilise une liste statique,
sans dépendance externe ni token.
"""
from datetime import datetime, timezone


def _article(source, title, summary, url=None, image=None):
    return {
        "source": source,
        "title": title,
        "summary": summary,
        "url": url,
        "image": image,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def fetch_news():
    """Retourne une liste d’articles (statiques pour l’instant)."""
    return {
        "articles": [
            _article(
                "NASA",
                "James Webb cartographie les colonnes de la Création en infrarouge",
                "Le télescope spatial James Webb révèle une structure fine des "
                "Colonnes de la Création, mettant en évidence les cocons de formation "
                "d’étoiles cachés dans la poussière.",
                "https://www.nasa.gov/",
                None,
            ),
            _article(
                "ESA",
                "Gaia publie un nouveau catalogue de plus de 1,8 milliard d’étoiles",
                "La mission Gaia affine les distances et mouvements des étoiles de la "
                "Voie lactée, offrant une vue 3D inédite de notre galaxie.",
                "https://www.esa.int/",
                None,
            ),
            _article(
                "SpaceFlight News",
                "Lancement réussi d’un lot de satellites d’observation de la Terre",
                "Une fusée commerciale a placé en orbite plusieurs satellites d’imagerie "
                "destinés au suivi du climat, des forêts et des océans.",
                "https://spaceflightnow.com/",
                None,
            ),
        ]
    }

