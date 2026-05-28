"""
app.services.news_i18n — traduction termes news (legacy extraite de station_web.py).

Sprint A · Tranche #3 (2026-05-28) — Extraction pure depuis le monolithe.

NOTE : le blueprint app/blueprints/feeds/__init__.py possède sa propre copie
locale des 2 symboles, utilisée en runtime par /api/live/news. Aucune
consolidation n'est faite à ce stade — cf. Sprint A bis pour réconciliation.

Le shim de compatibilité dans station_web.py re-importe ces symboles depuis
ce module pour préserver tout lazy-import legacy.
"""
from __future__ import annotations


_NEWS_TRADUCTIONS = {
    'launches': 'lancements',
    'satellite': 'satellite',
    'mission': 'mission',
    'rocket': 'fusée',
    'space': 'espace',
    'NASA': 'NASA',
    'SpaceX': 'SpaceX',
}


def _apply_news_translations(items):
    """Remplace quelques termes fréquents dans titres/résumés des news (ordre pour éviter space→SpaceX)."""
    if not items:
        return items
    order = ['SpaceX', 'NASA', 'launches', 'satellite', 'mission', 'rocket', 'space']
    tr = _NEWS_TRADUCTIONS
    out = []
    for a in items:
        title = a.get('title', '')
        summary = a.get('summary', '')
        for en in order:
            if en in tr:
                title = title.replace(en, tr[en])
                summary = summary.replace(en, tr[en])
        out.append({**a, 'title': title, 'summary': summary})
    return out

__all__ = ["_NEWS_TRADUCTIONS", "_apply_news_translations"]
