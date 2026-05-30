"""Unit tests — ce_soir.html ne doit JAMAIS revenir a une longitude
positive pour Tlemcen.

Bug historique : trois lignes (l.431 affichage, l.738 fetch sunrise/sunset,
l.783 fetch meteo courante) declaraient Tlemcen a longitude=+1.32 (~250 km
a l'est, centre Algerie) au lieu de -1.32 (Tlemcen, ouest de Greenwich).
Coordonnee canonique du codebase : app/constants/observatory.py:OBSERVER_LON
= -1.3167.

Ce fichier de tests refuse toute regression : pas de "longitude=1.32" sans
signe moins, pas de "1.32°E" pour Tlemcen, et toute mention Open-Meteo dans
ce_soir.html doit avoir une longitude negative ou explicitement non-Tlemcen.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


CE_SOIR = (
    Path(__file__).resolve().parents[2]
    / "templates" / "ce_soir.html"
)


def _source() -> str:
    return CE_SOIR.read_text(encoding="utf-8")


# ─── Sentinelles statiques ───────────────────────────────────────────────────


def test_no_positive_longitude_for_tlemcen_in_open_meteo_fetches():
    """Aucun fetch Open-Meteo avec latitude=34.87 ne doit avoir une
    longitude positive — Tlemcen est a l'ouest de Greenwich."""
    text = _source()
    # Match any open-meteo URL chained to latitude=34.87 then a longitude
    # that does NOT start with a minus sign.
    offenders = re.findall(
        r"api\.open-meteo\.com[^'\"\s]*latitude=34\.87[^'\"\s]*longitude=(?!-)[\d.]+",
        text,
    )
    assert not offenders, (
        f"Open-Meteo fetch avec longitude positive pour Tlemcen : {offenders}. "
        "Tlemcen est a l'ouest -> longitude doit etre negative."
    )


def test_no_east_label_for_tlemcen_in_display_text():
    """L'affichage texte 'Lat 34.87°N · X°E' est interdit pour Tlemcen :
    longitude positive (Est) contredit la realite geographique (Ouest)."""
    text = _source()
    # Catch "34.87°N · <something>°E" patterns.
    offenders = re.findall(r"34\.87\s*°\s*N[^<\n]{0,40}°\s*E", text)
    assert not offenders, (
        f"Etiquette '°E' associee a Tlemcen (34.87°N) trouvee : {offenders}. "
        "Tlemcen est a l'ouest -> utiliser °O (FR) ou °W (EN)."
    )


def test_open_meteo_fetches_use_consistent_tlemcen_longitude():
    """Toutes les URLs Open-Meteo qui ciblent lat=34.87 doivent partager
    la meme longitude (-1.32) — pas de divergence entre sunrise et meteo."""
    text = _source()
    longitudes = re.findall(
        r"api\.open-meteo\.com[^'\"\s]*latitude=34\.87[^'\"\s]*longitude=(-?[\d.]+)",
        text,
    )
    assert longitudes, "Aucun fetch Open-Meteo pour lat=34.87 trouve — refactor ?"
    unique = set(longitudes)
    assert unique == {"-1.32"}, (
        f"Longitudes Open-Meteo divergentes pour Tlemcen : {unique}. "
        "Doit etre exactement {-1.32} (cf. OBSERVER_LON dans "
        "app/constants/observatory.py)."
    )


def test_tlemcen_pill_coordinate_unchanged():
    """Le pill de selection Tlemcen doit garder data-lng='-1.32'."""
    text = _source()
    assert 'data-name="Tlemcen"' in text
    # Match the pill button line containing Tlemcen + verify data-lng is negative.
    m = re.search(r'data-lat="([\d.]+)"\s+data-lng="(-?[\d.]+)"\s+data-name="Tlemcen"', text)
    assert m, "Pill Tlemcen introuvable ou refactore — relire le test."
    assert m.group(1) == "34.87"
    assert m.group(2) == "-1.32", (
        f"Pill Tlemcen data-lng={m.group(2)!r}, attendu '-1.32'."
    )


def test_prayers_call_uses_negative_tlemcen_longitude():
    """loadCityPrayers(... Tlemcen ...) doit utiliser la longitude negative."""
    text = _source()
    m = re.search(
        r"loadCityPrayers\(\s*([\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*['\"]Tlemcen['\"]",
        text,
    )
    assert m, "Appel loadCityPrayers(...Tlemcen...) introuvable."
    assert m.group(1) == "34.87"
    assert m.group(2) == "-1.32"


def test_observer_lon_canonical_sign_negative():
    """Sanity : la source canonique elle-meme est negative.

    Si cette assertion echoue, c'est que quelqu'un a modifie
    app/constants/observatory.py, et il faut realigner ce_soir.html.
    """
    obs = (
        Path(__file__).resolve().parents[2]
        / "app" / "constants" / "observatory.py"
    ).read_text(encoding="utf-8")
    m = re.search(r"OBSERVER_LON\s*=\s*(-?[\d.]+)", obs)
    assert m, "OBSERVER_LON introuvable dans app/constants/observatory.py"
    assert float(m.group(1)) < 0, (
        f"OBSERVER_LON={m.group(1)} canonique attendu negatif "
        "(Tlemcen, ouest de Greenwich)."
    )
