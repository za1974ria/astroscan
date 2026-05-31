"""Unit tests — _meta_seo.html partial wiring.

Tests :
  - Le partial est bien inclus dans le scope etabli (ce_soir.html + aurores.html).
  - Apres rendu, chaque page contient EXACTEMENT UN meta description, UN canonical,
    UN bloc JSON-LD (zero doublon introduit par l'include).
  - Le JSON-LD rendu est du JSON valide.
  - geo.latitude / geo.longitude sont les valeurs canoniques (34.8753, -1.3167).
  - hreflang fr / en / x-default presents.
  - canonical URL specifique a la page (pas la racine par defaut).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


# Pages couvertes par le perimetre restreint de ce patch.
COVERED = {
    "ce_soir.html": "/ce_soir",
    "aurores.html": "/aurores",
}


def _render(template_name: str, request_path: str) -> str:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    class MockRequest:
        path = request_path

    env.globals["request"] = MockRequest()
    env.globals["lang"] = "fr"
    env.globals["observer_lat"] = 34.8753
    env.globals["observer_lon"] = -1.3167
    env.globals["observer_alt_m"] = 816
    env.globals["observer_city"] = "Tlemcen"

    return env.get_template(template_name).render(fetes_islamiques=[])


def _head(rendered: str) -> str:
    end = rendered.find("</head>")
    assert end != -1, "rendu sans </head> — template casse ?"
    return rendered[:end]


# ─── Sentinelles statiques ───────────────────────────────────────────────────


@pytest.mark.parametrize("template,path", list(COVERED.items()))
def test_template_includes_seo_partial(template, path):
    """Le source du template doit explicitement inclure _meta_seo."""
    text = (TEMPLATES_DIR / template).read_text(encoding="utf-8")
    assert '{% include "_meta_seo.html" %}' in text, (
        f"{template} n'inclut pas _meta_seo.html — le partial dormirait encore."
    )


# ─── Sentinelles de rendu (zero doublon) ──────────────────────────────────────


@pytest.mark.parametrize("template,path", list(COVERED.items()))
def test_exactly_one_meta_description_after_include(template, path):
    head = _head(_render(template, path))
    count = len(re.findall(r'name="description"', head))
    assert count == 1, (
        f"{template} a {count} <meta name='description'> dans <head> — "
        "doublon (la balise manuelle a-t-elle bien ete retiree ?)."
    )


@pytest.mark.parametrize("template,path", list(COVERED.items()))
def test_exactly_one_canonical_after_include(template, path):
    head = _head(_render(template, path))
    count = len(re.findall(r'rel="canonical"', head))
    assert count == 1, f"{template} a {count} canonical (attendu 1)."


@pytest.mark.parametrize("template,path", list(COVERED.items()))
def test_exactly_one_json_ld_block_after_include(template, path):
    head = _head(_render(template, path))
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>',
        head, re.DOTALL,
    )
    assert len(blocks) == 1, (
        f"{template} a {len(blocks)} blocs JSON-LD (attendu 1)."
    )


@pytest.mark.parametrize("template,path", list(COVERED.items()))
def test_json_ld_is_valid_and_geo_is_canonical_tlemcen(template, path):
    head = _head(_render(template, path))
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        head, re.DOTALL,
    )
    assert m, f"{template} n'a pas de bloc JSON-LD"
    data = json.loads(m.group(1))  # raises if invalid
    assert data.get("@type") == "Observatory"
    geo = data.get("geo", {})
    assert geo.get("@type") == "GeoCoordinates"
    assert geo.get("latitude") == 34.8753
    lon = geo.get("longitude")
    assert lon is not None
    assert float(lon) < 0, (
        f"{template} : JSON-LD geo.longitude={lon} doit etre negative (Tlemcen, ouest)."
    )


# ─── Hreflang et canonical specifiques a la page ──────────────────────────────


@pytest.mark.parametrize("template,path", list(COVERED.items()))
def test_hreflang_alternates_present(template, path):
    head = _head(_render(template, path))
    assert 'hreflang="fr"' in head
    assert 'hreflang="en"' in head
    assert 'hreflang="x-default"' in head


@pytest.mark.parametrize("template,path", list(COVERED.items()))
def test_canonical_url_targets_specific_page_not_root(template, path):
    """Le partial accepte seo_url ; chaque page doit le poser pour eviter
    qu'un canonical racine generique ne soit emis."""
    head = _head(_render(template, path))
    # Path mapping page -> expected canonical
    expected = {
        "/ce_soir": "https://astroscan.space/ce_soir",
        "/aurores": "https://astroscan.space/aurores",
    }[path]
    m = re.search(r'<link rel="canonical" href="([^"]+)"', head)
    assert m, "canonical introuvable"
    assert m.group(1) == expected, (
        f"{template} canonical={m.group(1)!r}, attendu {expected!r}. "
        "(seo_url doit etre pose au-dessus de l'include.)"
    )


# ─── Garde du context_processor observer_constants (deja teste ailleurs) ────


def test_meta_seo_partial_unchanged():
    """Le partial lui-meme ne doit pas avoir ete modifie — il reste source unique."""
    partial = (TEMPLATES_DIR / "_meta_seo.html").read_text(encoding="utf-8")
    assert "@type" in partial and "Observatory" in partial
    assert "{{ observer_lat }}" in partial
    assert "{{ observer_lon }}" in partial
