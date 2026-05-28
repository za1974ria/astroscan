"""Independent-reference tests for app.services.hilal_compute.

Principe : aucune assertion ne compare hilal_compute à lui-même.
Chaque test s'appuie sur une référence INDÉPENDANTE :

- **NASA Eclipse / IMCCE** — dates de nouvelles lunes publiées (oracle externe).
  Référence : https://eclipse.gsfc.nasa.gov/phase/phasescat.html
- **skyfield + de421.bsp** — recalcul de l'élongation Lune-Soleil par une
  bibliothèque qui n'utilise NI ephem NI astropy en interne (oracle indépendant).
- **Propriétés physiques** — invariants cinématiques et géométriques
  (ARCL ≥ 0, lune s'éloigne du soleil après conjonction, ω_lune−ω_soleil ≈ 12°/j,
  formule Odeh W = 0.27245·(1−cos(ARCL))).
- **Règles déterministes des critères** — seuils Odeh 2006 et UIOF, qui sont
  des règles externes au calcul astronomique.

Les coords Tlemcen viennent de OBSERVER_LAT/LON/ALT_M, déjà testés contre
des valeurs publiées par tests/unit/test_observatory_constants.py.
"""

from __future__ import annotations

import math
import os
from datetime import UTC, date, datetime

import pytest

from app.constants.observatory import OBSERVER_ALT_M, OBSERVER_LAT, OBSERVER_LON
from app.services.hilal_compute import hilal_compute

# ─── Référence externe : nouvelles lunes (NASA Eclipse / IMCCE) ──────────────
# Source publiée : https://eclipse.gsfc.nasa.gov/phase/phasescat.html
# Format : (date d'entrée "around", date+heure UTC de la prochaine nouvelle lune).
# Tolérance ±1 minute (les sources NASA ont une précision minute, ephem aussi).
NEW_MOONS_REF = [
    (date(2025, 1, 25), datetime(2025, 1, 29, 12, 36, tzinfo=UTC)),
    (date(2025, 3, 20), datetime(2025, 3, 29, 10, 58, tzinfo=UTC)),
    (date(2025, 8, 15), datetime(2025, 8, 23, 6, 7, tzinfo=UTC)),
    (date(2026, 2, 1), datetime(2026, 2, 17, 12, 1, tzinfo=UTC)),
]


# ─── Fixture skyfield oracle (skip si pas dispo) ──────────────────────────────


@pytest.fixture(scope="module")
def skyfield_oracle():
    """Charge skyfield + de421.bsp pour calculer l'élongation indépendamment.

    Skip clean si skyfield n'est pas installé ou si de421.bsp est absent
    (typique de CI sans data téléchargée).
    """
    bsp_path = "/root/astro_scan/de421.bsp"
    if not os.path.exists(bsp_path):
        pytest.skip(f"de421.bsp absent ({bsp_path}) — skyfield cross-check skipped")
    try:
        from skyfield.api import load, load_file
    except ImportError:
        pytest.skip("skyfield not installed — cross-check skipped")
    eph = load_file(bsp_path)
    ts = load.timescale(builtin=True)
    return eph, ts


# ─── 1. Structure de la sortie ────────────────────────────────────────────────


def test_returns_well_formed_dict():
    res = hilal_compute(date(2026, 2, 1))
    assert isinstance(res, dict)
    assert res["ok"] is True
    for key in (
        "location",
        "hijri_current",
        "new_moon",
        "sighting_days",
        "predicted_first_day",
        "countdown_days",
    ):
        assert key in res, f"missing top-level key: {key}"
    assert isinstance(res["sighting_days"], list)
    # 2 entrées : jour J (nouvelle lune) + J+1
    assert len(res["sighting_days"]) == 2


def test_sighting_day_record_shape():
    res = hilal_compute(date(2026, 2, 1))
    rec = res["sighting_days"][0]
    for key in (
        "date",
        "sunset_utc",
        "moonset_utc",
        "moon_alt_deg",
        "moon_az_deg",
        "arcl_deg",
        "arcv_deg",
        "crescent_width_arcmin",
        "crescent_width_deg",
        "moon_age_hours",
        "criteria",
    ):
        assert key in rec, f"missing sighting_day key: {key}"
    for crit_key in ("odeh", "uiof", "oum_al_qura"):
        assert crit_key in rec["criteria"]


# ─── 2. Coords Tlemcen vs constants observatoire (source unique de vérité) ────


def test_location_matches_observatory_constants():
    """hilal_compute doit exposer les coords de OBSERVER_LAT/LON/ALT_M.
    Pas tautologique : vérifie le câblage du module sur la SOURCE UNIQUE
    (cf. app/constants/observatory.py, déjà testé contre valeurs publiées).
    """
    res = hilal_compute(date(2026, 2, 1))
    loc = res["location"]
    assert loc["city"] == "Tlemcen"
    assert loc["lat"] == OBSERVER_LAT
    assert loc["lon"] == OBSERVER_LON
    assert loc["alt_m"] == OBSERVER_ALT_M
    # Garde-fou anti-Tiaret : Tlemcen est OUEST de Greenwich → lon négatif
    assert loc["lon"] < 0, "Lon Tlemcen doit être négatif (ouest Greenwich)"


# ─── 3. New moons vs NASA Eclipse (référence externe) ────────────────────────


@pytest.mark.parametrize("input_date,expected_nm_utc", NEW_MOONS_REF)
def test_next_new_moon_matches_nasa_reference(input_date, expected_nm_utc):
    """La prochaine nouvelle lune calculée par hilal_compute doit matcher la
    date publiée par NASA Eclipse à ±1 minute près.

    Référence externe : https://eclipse.gsfc.nasa.gov/phase/phasescat.html
    """
    res = hilal_compute(input_date)
    nm_calc = datetime.fromisoformat(res["new_moon"]["datetime_utc"])
    delta_s = abs((nm_calc - expected_nm_utc).total_seconds())
    assert delta_s < 60.0, (
        f"new moon mismatch for input {input_date}: "
        f"calc={nm_calc.isoformat()} expected={expected_nm_utc.isoformat()} "
        f"delta={delta_s:.1f}s"
    )


# ─── 4. Cross-check skyfield (élongation indépendante) ───────────────────────


def test_arcl_cross_check_with_skyfield(skyfield_oracle):
    """L'élongation ARCL retournée par hilal_compute doit matcher le calcul
    skyfield à ±0.5° près. Skyfield n'utilise NI ephem NI astropy — c'est un
    oracle de référence indépendant des deux bibliothèques internes de hilal.
    Tolérance 0.5° absorbe les différences de modèle d'éphéméride.
    """
    eph, ts = skyfield_oracle
    res = hilal_compute(date(2026, 2, 1))
    earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]

    for day_record in res["sighting_days"]:
        day = date.fromisoformat(day_record["date"])
        # parse "HH:MM UTC"
        hh, mm = map(int, day_record["sunset_utc"].split()[0].split(":"))
        sunset = datetime(day.year, day.month, day.day, hh, mm, tzinfo=UTC)
        t = ts.from_datetime(sunset)
        sun_pos = earth.at(t).observe(sun).apparent()
        moon_pos = earth.at(t).observe(moon).apparent()
        arcl_skyfield = sun_pos.separation_from(moon_pos).degrees
        arcl_hilal = day_record["arcl_deg"]
        diff = abs(arcl_hilal - arcl_skyfield)
        assert diff < 0.5, (
            f"ARCL mismatch on {day}: hilal={arcl_hilal:.3f}° "
            f"skyfield={arcl_skyfield:.3f}° diff={diff:.3f}°"
        )


# ─── 5. Propriétés physiques (invariants cinématiques) ───────────────────────


def test_arcl_near_zero_at_new_moon_day():
    """Le jour de la nouvelle lune au coucher du soleil, ARCL doit être petit
    (< 10°). Propriété astronomique : juste après conjonction, la Lune ne
    s'écarte que de quelques degrés (~12°/jour, donc ~6h après conjonction
    elle est à 3-4°).
    """
    res = hilal_compute(date(2026, 2, 1))
    arcl_day0 = res["sighting_days"][0]["arcl_deg"]
    assert 0.0 <= arcl_day0 < 10.0, f"ARCL J0 hors plage physique: {arcl_day0}"


def test_arcl_grows_between_J_and_J_plus_1():
    """Entre J (jour nouvelle lune) et J+1, la Lune s'éloigne du Soleil.
    Cinématique : la vitesse différentielle Lune−Soleil vaut ≈ 12.2°/jour.
    On attend arcl(J+1) > arcl(J), avec delta dans [7°, 18°].
    """
    res = hilal_compute(date(2026, 2, 1))
    arcl0 = res["sighting_days"][0]["arcl_deg"]
    arcl1 = res["sighting_days"][1]["arcl_deg"]
    assert arcl1 > arcl0, f"ARCL doit croître: J0={arcl0} J+1={arcl1}"
    delta = arcl1 - arcl0
    assert 7.0 < delta < 18.0, f"Delta ARCL J→J+1 hors cinématique attendue: {delta:.2f}°"


def test_moon_age_increases_by_about_24h():
    """L'âge de la Lune (heures depuis nouvelle lune) doit augmenter d'environ
    24h entre J et J+1. Vérifie que hilal_compute pose bien l'origine au
    moment de la conjonction et non à minuit.
    """
    res = hilal_compute(date(2026, 2, 1))
    age0 = res["sighting_days"][0]["moon_age_hours"]
    age1 = res["sighting_days"][1]["moon_age_hours"]
    assert age0 >= 0
    assert 22.0 < (age1 - age0) < 26.0, f"Delta âge inattendu: {age1 - age0}h"


# ─── 6. Formule Odeh : W = 0.27245 * (1 - cos(ARCL)) ─────────────────────────


def test_crescent_width_follows_odeh_formula():
    """La largeur du croissant W doit obéir à W = 0.27245 · (1 − cos(ARCL))
    (formule Odeh 2006). On recalcule indépendamment avec math.cos et on
    compare à crescent_width_deg.
    """
    res = hilal_compute(date(2026, 2, 1))
    for r in res["sighting_days"]:
        arcl = r["arcl_deg"]
        w_expected = 0.27245 * (1.0 - math.cos(math.radians(arcl)))
        w_got = r["crescent_width_deg"]
        assert abs(w_got - w_expected) < 0.001, (
            f"Crescent width hors formule Odeh: got={w_got} expected={w_expected:.6f}"
        )


# ─── 7. Règles déterministes des critères (seuils externes au calcul) ────────


def test_odeh_cannot_be_visible_below_arcl_threshold():
    """Règle du critère Odeh 2006 : ARCL < 6.4° ⇒ pas de "VISIBLE"."""
    res = hilal_compute(date(2026, 2, 1))
    for r in res["sighting_days"]:
        if r["arcl_deg"] < 6.4:
            assert r["criteria"]["odeh"] != "VISIBLE", (
                f"Violation Odeh: ODEH=VISIBLE pour ARCL={r['arcl_deg']}° < 6.4°"
            )


def test_uiof_cannot_be_visible_below_arcv_threshold():
    """Règle du critère UIOF / France : ARCV < 5° ⇒ pas de "VISIBLE"."""
    res = hilal_compute(date(2026, 2, 1))
    for r in res["sighting_days"]:
        if r["arcv_deg"] < 5.0:
            assert r["criteria"]["uiof"] != "VISIBLE", (
                f"Violation UIOF: UIOF=VISIBLE pour ARCV={r['arcv_deg']}° < 5°"
            )


def test_criteria_use_known_labels_only():
    """Chaque critère doit renvoyer une valeur dans un ensemble fermé connu."""
    res = hilal_compute(date(2026, 2, 1))
    odeh_set = {"VISIBLE", "INCERTAIN", "POSSIBLE", "NON VISIBLE"}
    uiof_set = {"VISIBLE", "INCERTAIN", "NON VISIBLE"}
    oum_set = {"VISIBLE", "INCERTAIN", "NON VISIBLE"}
    for r in res["sighting_days"]:
        c = r["criteria"]
        assert c["odeh"] in odeh_set, f"odeh hors ensemble: {c['odeh']}"
        assert c["uiof"] in uiof_set, f"uiof hors ensemble: {c['uiof']}"
        assert c["oum_al_qura"] in oum_set, f"oum_al_qura hors ensemble: {c['oum_al_qura']}"


# ─── 8. Cohérence du compte à rebours et du calendrier hégire ────────────────


def test_predicted_first_day_is_after_or_on_new_moon():
    """Le 1er jour du mois hégirien prédit doit être >= la date de nouvelle lune.
    Propriété logique : le croissant n'est pas observable AVANT la conjonction.
    """
    res = hilal_compute(date(2026, 2, 1))
    nm_date = date.fromisoformat(res["new_moon"]["date"])
    pred_date = date.fromisoformat(res["predicted_first_day"])
    assert pred_date >= nm_date, f"predicted_first_day {pred_date} < new_moon date {nm_date}"


def test_hijri_month_name_in_canonical_list():
    """Le nom du mois hégirien doit être dans la liste canonique des 12 mois."""
    canonical = {
        "Mouharram",
        "Safar",
        "Rabi al-Awwal",
        "Rabi al-Thani",
        "Joumada al-Oula",
        "Joumada al-Thania",
        "Rajab",
        "Chaabane",
        "Ramadan",
        "Chawwal",
        "Dhou al-Qi'da",
        "Dhou al-Hijja",
    }
    res = hilal_compute(date(2026, 2, 1))
    assert res["hijri_current"]["month_name"] in canonical
    assert res["next_month_name"] in canonical
    # Mois indexé 1..12
    assert 1 <= res["hijri_current"]["month_num"] <= 12


# ─── 9. Default for_date = aujourd'hui (sanity sans tautologie) ──────────────


def test_default_for_date_is_today_utc():
    """Si for_date=None, le module doit utiliser la date UTC du jour.
    On vérifie que computed_at est proche de maintenant (< 60s).
    """
    res = hilal_compute()  # for_date None
    computed = datetime.fromisoformat(res["computed_at"])
    now = datetime.now(UTC)
    assert abs((now - computed).total_seconds()) < 60.0
    assert res["ok"] is True
