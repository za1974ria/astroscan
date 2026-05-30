"""Unit tests — Global Threat Index single source of truth.

Couvre :
  - normalize_* (kp / xray / seismic / air / tle_age)
  - compute_threat_index nominal (toutes composantes presentes)
  - chemins degrades (1 manquant, plusieurs manquants, tous manquants)
  - coherence formule HTML methodology vs poids/bornes Python
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from mission_control.backend.app.services.threat_index import (
    KP_RANGE,
    TLE_AGE_HOURS_MAX,
    WEIGHTS_NOMINAL,
    XRAY_LOG_RANGE,
    compute_threat_index,
    normalize_air,
    normalize_kp,
    normalize_seismic,
    normalize_tle_age,
    normalize_xray,
)


# ---------------------------------------------------------------------------
# normalize_kp
# ---------------------------------------------------------------------------


class TestNormalizeKp:
    def test_lower_bound(self):
        assert normalize_kp(0) == 0.0

    def test_upper_bound(self):
        assert normalize_kp(9) == 100.0

    def test_midpoint(self):
        assert normalize_kp(4.5) == pytest.approx(50.0)

    def test_above_range_clamps(self):
        assert normalize_kp(12) == 100.0

    def test_below_range_clamps(self):
        assert normalize_kp(-3) == 0.0

    def test_none_returns_none(self):
        assert normalize_kp(None) is None

    def test_non_numeric_returns_none(self):
        assert normalize_kp("nope") is None

    def test_nan_returns_none(self):
        assert normalize_kp(float("nan")) is None

    def test_int_accepted(self):
        assert normalize_kp(3) == pytest.approx(3 / 9 * 100)


# ---------------------------------------------------------------------------
# normalize_xray
# ---------------------------------------------------------------------------


class TestNormalizeXray:
    def test_a_class_floor(self):
        assert normalize_xray(1e-8) == 0.0

    def test_x_class_ceiling(self):
        assert normalize_xray(1e-3) == 100.0

    def test_midpoint_log(self):
        # log10(10**-5.5) = -5.5; (-5.5+8)/5*100 = 50
        assert normalize_xray(10 ** -5.5) == pytest.approx(50.0)

    def test_below_floor_clamps(self):
        assert normalize_xray(1e-12) == 0.0

    def test_above_ceiling_clamps(self):
        assert normalize_xray(1e-1) == 100.0

    def test_zero_treated_as_quiet(self):
        # log10(0) undefined; honest semantics: quiet sun -> 0% threat.
        assert normalize_xray(0) == 0.0

    def test_negative_treated_as_quiet(self):
        assert normalize_xray(-1e-7) == 0.0

    def test_none_returns_none(self):
        assert normalize_xray(None) is None


# ---------------------------------------------------------------------------
# normalize_seismic / normalize_air (pass-through clamps)
# ---------------------------------------------------------------------------


class TestNormalizeSeismic:
    def test_passthrough_in_range(self):
        assert normalize_seismic(42.5) == 42.5

    def test_clamps_upper(self):
        assert normalize_seismic(180) == 100.0

    def test_clamps_lower(self):
        assert normalize_seismic(-10) == 0.0

    def test_none(self):
        assert normalize_seismic(None) is None


class TestNormalizeAir:
    def test_passthrough(self):
        assert normalize_air(67.0) == 67.0

    def test_clamps_upper(self):
        assert normalize_air(200) == 100.0

    def test_none(self):
        assert normalize_air(None) is None


# ---------------------------------------------------------------------------
# normalize_tle_age
# ---------------------------------------------------------------------------


class TestNormalizeTleAge:
    def test_fresh_zero(self):
        assert normalize_tle_age(0) == 0.0

    def test_max_saturated(self):
        assert normalize_tle_age(TLE_AGE_HOURS_MAX) == 100.0

    def test_beyond_max_clamps(self):
        assert normalize_tle_age(120) == 100.0

    def test_negative_clamps_to_zero(self):
        # Clock skew safety: never produce a negative threat.
        assert normalize_tle_age(-3) == 0.0

    def test_midpoint(self):
        assert normalize_tle_age(24) == pytest.approx(50.0)

    def test_none(self):
        assert normalize_tle_age(None) is None


# ---------------------------------------------------------------------------
# compute_threat_index — nominal
# ---------------------------------------------------------------------------


class TestComputeThreatIndexNominal:
    def test_full_live(self):
        res = compute_threat_index({
            "kp": 4.5,
            "xray_wm2": 10 ** -5.5,
            "seismic_score": 50,
            "air_density_pct": 75,
            "tle_age_hours": 24,
        })
        # 0.35*50 + 0.20*50 + 0.25*50 + 0.10*75 + 0.10*50 = 52.5
        assert res["state"] == "live"
        assert res["missing"] == []
        assert res["index"] == pytest.approx(52.5)
        assert res["weights_sum_effective"] == pytest.approx(1.0)
        # Effective weights == nominal when nothing is missing
        for name, weight in WEIGHTS_NOMINAL.items():
            comp = res["components"][name]
            assert comp["available"] is True
            assert comp["weight_effective"] == pytest.approx(weight)

    def test_all_zero_components(self):
        res = compute_threat_index({
            "kp": 0,
            "xray_wm2": 1e-8,
            "seismic_score": 0,
            "air_density_pct": 0,
            "tle_age_hours": 0,
        })
        assert res["state"] == "live"
        assert res["index"] == 0.0

    def test_all_maxed(self):
        res = compute_threat_index({
            "kp": 9,
            "xray_wm2": 1e-3,
            "seismic_score": 100,
            "air_density_pct": 100,
            "tle_age_hours": TLE_AGE_HOURS_MAX,
        })
        assert res["state"] == "live"
        assert res["index"] == 100.0


# ---------------------------------------------------------------------------
# compute_threat_index — degraded (1+ missing) and unavailable
# ---------------------------------------------------------------------------


class TestComputeThreatIndexDegraded:
    def test_single_missing_renormalizes(self):
        # kp missing -> remaining weights (0.20+0.25+0.10+0.10) = 0.65
        # All other components forced to 50 -> weighted_sum = 0.65*50 = 32.5
        # index = 32.5 / 0.65 = 50.0
        res = compute_threat_index({
            "kp": None,
            "xray_wm2": 10 ** -5.5,
            "seismic_score": 50,
            "air_density_pct": 50,
            "tle_age_hours": 24,
        })
        assert res["state"] == "degraded"
        assert res["missing"] == ["kp"]
        assert res["index"] == pytest.approx(50.0)
        # Effective weights of available components must resum to 1.0
        total_effective = sum(
            c["weight_effective"] for c in res["components"].values() if c["available"]
        )
        assert total_effective == pytest.approx(1.0)
        # kp component still reported with weight_effective = 0
        assert res["components"]["kp"]["weight_effective"] == 0.0
        assert res["components"]["kp"]["available"] is False

    def test_multi_missing(self):
        # Only seismic + air available (weights 0.25 + 0.10 = 0.35)
        res = compute_threat_index({
            "kp": None,
            "xray_wm2": None,
            "seismic_score": 80,
            "air_density_pct": 40,
            "tle_age_hours": None,
        })
        assert res["state"] == "degraded"
        assert set(res["missing"]) == {"kp", "xray", "tle_age"}
        # weighted_sum = 0.25*80 + 0.10*40 = 20 + 4 = 24
        # index = 24 / 0.35 = 68.5714...
        assert res["index"] == pytest.approx(24 / 0.35, abs=0.01)
        assert res["weights_sum_effective"] == pytest.approx(0.35)

    def test_all_missing_unavailable(self):
        res = compute_threat_index({})
        assert res["state"] == "unavailable"
        assert res["index"] is None
        assert set(res["missing"]) == set(WEIGHTS_NOMINAL.keys())
        assert res["weights_sum_effective"] == 0.0

    def test_all_explicit_none_unavailable(self):
        res = compute_threat_index({
            "kp": None,
            "xray_wm2": None,
            "seismic_score": None,
            "air_density_pct": None,
            "tle_age_hours": None,
        })
        assert res["state"] == "unavailable"
        assert res["index"] is None

    def test_partial_payload_keys(self):
        # Only kp provided; honest degraded result.
        res = compute_threat_index({"kp": 9})
        assert res["state"] == "degraded"
        assert res["index"] == 100.0  # 0.35 weight renormalized to 1.0
        assert res["components"]["kp"]["weight_effective"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Coherence formule HTML methodology <-> module Python
# ---------------------------------------------------------------------------


class TestMethodologyCoherence:
    METHODOLOGY_HTML = (
        Path(__file__).resolve().parents[2] / "templates" / "methodology.html"
    )

    def test_html_lists_exact_weights(self):
        text = self.METHODOLOGY_HTML.read_text(encoding="utf-8")
        # Block <pre>threat_index = ... </pre>
        m = re.search(r"<pre>threat_index =(.+?)</pre>", text, re.DOTALL)
        assert m, "Bloc formule threat_index introuvable dans methodology.html"
        block = m.group(1)
        # On extrait les poids puis on les compare aux constantes Python.
        # Lignes du type "0.35 * normalize(noaa_kp, 0, 9)"
        weights_html = [float(x) for x in re.findall(r"\b(0\.\d+)\s*\*", block)]
        weights_py = list(WEIGHTS_NOMINAL.values())
        assert weights_html == weights_py, (
            f"Poids HTML {weights_html} != module Python {weights_py}"
        )

    def test_html_lists_kp_bounds(self):
        text = self.METHODOLOGY_HTML.read_text(encoding="utf-8")
        # "normalize(noaa_kp, 0, 9)"
        m = re.search(r"normalize\(noaa_kp,\s*(\d+),\s*(\d+)\)", text)
        assert m, "Bornes Kp introuvables dans methodology.html"
        lo, hi = float(m.group(1)), float(m.group(2))
        assert (lo, hi) == KP_RANGE

    def test_html_lists_xray_log_bounds(self):
        text = self.METHODOLOGY_HTML.read_text(encoding="utf-8")
        # "normalize(log10(xray_wm2), -8, -3)"
        m = re.search(
            r"normalize\(log10\(xray_wm2\),\s*(-?\d+),\s*(-?\d+)\)", text
        )
        assert m, "Bornes log10(xray) introuvables dans methodology.html"
        lo, hi = float(m.group(1)), float(m.group(2))
        assert (lo, hi) == XRAY_LOG_RANGE

    def test_html_lists_tle_age_cap(self):
        text = self.METHODOLOGY_HTML.read_text(encoding="utf-8")
        # "min(48, tle_age_hours) / 48 * 100"
        m = re.search(r"min\((\d+),\s*tle_age_hours\)\s*/\s*(\d+)", text)
        assert m, "Plafond TLE age introuvable dans methodology.html"
        cap_lo, cap_hi = float(m.group(1)), float(m.group(2))
        assert cap_lo == cap_hi == TLE_AGE_HOURS_MAX
