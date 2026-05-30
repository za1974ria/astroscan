"""Unit tests — Aucun template ne doit revenir a une longitude positive
pour Tlemcen.

Bug historique : 6 templates affichaient Tlemcen avec longitude=+1.32 ou
+1.3154 et le suffixe °E (centre Algerie, ~250 km a l'est de la vraie
position), alors que :
  - app/constants/observatory.py:OBSERVER_LON = -1.3167 (negatif, ouest).
  - Le backend (astro/__init__.py:76) calcule deja juste depuis cette
    source — c'etait uniquement l'affichage qui mentait.

Architecture : app/hooks.py:_inject_observer_constants enregistre un
context_processor global qui pose observer_lat, observer_lon,
observer_alt_m, observer_city dans TOUS les templates. Les templates
doivent consommer ces variables, pas hardcoder.

Sentinelles statiques (regex sur les sources templates).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

# Templates couverts par le fix initial + un trouve en passant (_meta_seo).
COVERED_TEMPLATES = [
    "a_propos.html",
    "about.html",
    "aurores.html",
    "data_export.html",
    "ephemerides.html",
    "observatoire.html",
    "_meta_seo.html",
    "ce_soir.html",  # fix anterieur (commit 115e4d1)
]


def _read(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


# ─── Sentinelle 1 : aucun "X.XX°E" pour Tlemcen ───────────────────────────────


def test_no_east_suffix_on_tlemcen_longitude_anywhere_in_templates():
    """Aucun template ne doit afficher Tlemcen avec un suffixe °E.

    Pattern : (lat-Tlemcen ~ 34.87 / 34.88 / 34.8731 / 34.8753) suivi a
    courte distance d'une longitude de la forme 1.xx avec °E.
    """
    pattern = re.compile(
        r"34\.8[78]\d{0,2}\s*°\s*N[^<\n]{0,80}1\.3\d*\s*°\s*E",
        re.IGNORECASE,
    )
    offenders = []
    for tmpl in TEMPLATES_DIR.rglob("*.html"):
        # Ignore les snapshots historiques.
        if any(s in tmpl.name for s in (".bak", ".verrou", ".old")):
            continue
        text = tmpl.read_text(encoding="utf-8", errors="ignore")
        for m in pattern.finditer(text):
            offenders.append((tmpl.relative_to(TEMPLATES_DIR.parent), m.group(0)[:80]))
    assert not offenders, (
        "Longitude positive (°E) pour Tlemcen detectee dans des templates :\n"
        + "\n".join(f"  {t}: {snippet}" for t, snippet in offenders)
    )


def test_no_isolated_degree_E_on_known_template_lines():
    """Pour les 7 templates couverts, aucune chaine litterale 'X.XX° E' ou
    'X.XX°E' avec X dans [1] ne doit subsister, meme isolee de la latitude."""
    pattern = re.compile(r"1\.3\d*\s*°\s*E\b")
    offenders = []
    for name in COVERED_TEMPLATES:
        text = _read(name)
        for m in pattern.finditer(text):
            offenders.append((name, m.group(0)))
    assert not offenders, (
        "Suffixe '°E' pour longitude Tlemcen trouve :\n"
        + "\n".join(f"  {t}: {s}" for t, s in offenders)
    )


# ─── Sentinelle 2 : aucun fetch JS avec longitude positive 1.xx ──────────────


def test_no_open_meteo_or_url_with_positive_longitude_for_tlemcen():
    """Aucun fetch URL (ouvert longitude=1.xx sans signe moins) ne doit
    subsister dans les templates (couvre ce_soir.html + futurs)."""
    pattern = re.compile(r"longitude=1\.[0-9]")
    offenders = []
    for tmpl in TEMPLATES_DIR.rglob("*.html"):
        if any(s in tmpl.name for s in (".bak", ".verrou", ".old")):
            continue
        text = tmpl.read_text(encoding="utf-8", errors="ignore")
        for m in pattern.finditer(text):
            offenders.append((tmpl.relative_to(TEMPLATES_DIR.parent), m.group(0)))
    assert not offenders, (
        "URL avec longitude=1.x (positif) trouvee — Tlemcen est a l'ouest :\n"
        + "\n".join(f"  {t}: {s}" for t, s in offenders)
    )


# ─── Sentinelle 3 : JSON-LD SEO doit avoir une longitude negative ────────────


def test_meta_seo_json_ld_longitude_is_dynamic_and_negative_source():
    """Le bloc JSON-LD GeoCoordinates de _meta_seo.html doit lire
    observer_lon (source canonique negative), pas un litteral positif."""
    text = _read("_meta_seo.html")
    # Match GeoCoordinates block then check longitude expression.
    m = re.search(
        r'"@type"\s*:\s*"GeoCoordinates"[\s\S]{0,200}?"longitude"\s*:\s*([^,\n}]+)',
        text,
    )
    assert m, "Bloc GeoCoordinates introuvable dans _meta_seo.html"
    longitude_expr = m.group(1).strip()
    # Accept either a Jinja expression that resolves to observer_lon, or a
    # literal negative number. Refuse positive literals.
    is_jinja_observer_lon = "observer_lon" in longitude_expr
    is_negative_literal = bool(re.match(r"^-\d", longitude_expr))
    assert is_jinja_observer_lon or is_negative_literal, (
        f'JSON-LD longitude = {longitude_expr!r} — doit etre {{{{ observer_lon }}}} '
        "ou un litteral negatif (Tlemcen, ouest)."
    )


# ─── Sentinelle 4 : les templates fixes utilisent bien observer_lon ───────────


def test_each_fixed_template_references_observer_lon():
    """Pour eviter les regressions par reintroduction d'un litteral, chaque
    template du lot doit consommer observer_lon (preuve qu'il passe par la
    source canonique injectee via hooks.py)."""
    missing = []
    for name in COVERED_TEMPLATES:
        # ce_soir.html est ignore pour cette assertion : son fix anterieur
        # utilise des litteraux -1.32 directement dans des URLs fetch, sans
        # passer par observer_lon (couvert par test_cesoir_tlemcen_longitude.py).
        if name == "ce_soir.html":
            continue
        text = _read(name)
        if "observer_lon" not in text:
            missing.append(name)
    assert not missing, (
        f"Templates qui ne referencent pas observer_lon : {missing}. "
        "Sans cette reference, un litteral fausse peut etre reintroduit "
        "sans qu'un test ne l'attrape."
    )


# ─── Sentinelle 5 : la constante canonique reste negative ────────────────────


def test_observer_lon_canonical_is_negative():
    obs = (TEMPLATES_DIR.parent / "app" / "constants" / "observatory.py").read_text(encoding="utf-8")
    m = re.search(r"OBSERVER_LON\s*=\s*(-?[\d.]+)", obs)
    assert m, "OBSERVER_LON introuvable dans app/constants/observatory.py"
    assert float(m.group(1)) < 0, (
        f"OBSERVER_LON = {m.group(1)} canonique attendu negatif (Tlemcen, ouest)."
    )


# ─── Sentinelle 6 : context_processor de hooks.py reste cable ────────────────


def test_observer_constants_context_processor_remains_wired():
    """Si quelqu'un debranche _inject_observer_constants, tous les templates
    qui consomment observer_lon redeviennent vides -> regression silencieuse."""
    hooks = (TEMPLATES_DIR.parent / "app" / "hooks.py").read_text(encoding="utf-8")
    assert "_inject_observer_constants" in hooks
    assert re.search(
        r"app\.context_processor\(\s*_inject_observer_constants\s*\)", hooks
    ), "Le context_processor _inject_observer_constants n'est plus enregistre."
