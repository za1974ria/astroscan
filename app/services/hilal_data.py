"""
app.services.hilal_data — Données Hilal (fêtes islamiques) + helper région.

Sprint A · Tranche #5 (2026-05-28) — Extraction pure depuis station_web.py.

NOTE : ces symboles sont déjà dupliqués en runtime dans les modules suivants
(consommateurs réels en production) :
    - FETES_ISLAMIQUES → app/blueprints/pages/__init__.py (route /ce_soir)
    - _guess_region    → app/services/iss_live.py (helpers ISS)

Aucune consolidation n'est faite à ce stade — cf. Sprint A bis pour
réconciliation. Le shim dans station_web.py re-importe ces symboles depuis
ce module pour préserver tout lazy-import legacy.
"""
from __future__ import annotations


def _guess_region(lat, lon):
    """Estimation grossière de la région survolée."""
    if -60 < lat < 60:
        if -30 < lon < 60:
            return 'Afrique / Europe'
        elif 60 < lon < 150:
            return 'Asie'
        elif -150 < lon < -30:
            return 'Amériques'
        else:
            return 'Océan Pacifique'
    elif lat >= 60:
        return 'Arctique'
    else:
        return 'Antarctique'


# Fêtes islamiques (année grégorienne 2026 / hégirien 1447–1448) — module El Hilal /ce_soir
FETES_ISLAMIQUES = [
    {
        "nom": "1er Mouharram",
        "nom_ar": "رأس السنة الهجرية",
        "description": "Nouvel An hégirien — début de l'année 1448",
        "date_2026": "2026-06-17",
        "hijri": "1 Mouharram 1448",
    },
    {
        "nom": "Achoura",
        "nom_ar": "عاشوراء",
        "description": "10ème jour de Mouharram — jour de jeûne recommandé",
        "date_2026": "2026-06-26",
        "hijri": "10 Mouharram 1448",
    },
    {
        "nom": "Mawlid Ennabawi",
        "nom_ar": "المولد النبوي الشريف",
        "description": "Naissance du Prophète Muhammad ﷺ",
        "date_2026": "2026-09-13",
        "hijri": "12 Rabi al-Awwal 1448",
    },
]

__all__ = ["FETES_ISLAMIQUES", "_guess_region"]
