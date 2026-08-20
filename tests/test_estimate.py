"""F07 pre-flight analytical estimates: idealizations + divergence band."""

from __future__ import annotations

import pytest

from companion.tools import estimate
from companion.tools.cad_fea import analytical_cantilever_stress

XTRUSS_GEOMETRY = {
    "part": "brake_pedal",
    "web_type": "xtruss",
    "cell_size_mm": 15.0,
    "strut_radius_mm": 2.5,
}

SOLID_GEOMETRY = {**XTRUSS_GEOMETRY, "web_type": "solid"}


def test_brake_pedal_estimate_value():
    # Overhang cantilever from the clevis: 6*500*121.66 / (36 * 15^2) ≈ 45.06 MPa.
    sigma, assumptions = estimate.brake_pedal_expected_mpa(500.0)
    assert sigma == pytest.approx(45.06, abs=0.2)
    assert "clevis" in assumptions


def test_cantilever_estimate_matches_analytical_reference():
    sigma, _ = estimate.cantilever_expected_mpa(100.0, 20.0, 5.0, 100.0)
    reference = analytical_cantilever_stress(100.0, 20.0, 5.0, 100.0)
    assert sigma == pytest.approx(reference["max_von_mises_mpa"], abs=1e-3)


def test_expected_vs_actual_band_and_flag():
    live = estimate.expected_vs_actual(
        "brake_pedal", XTRUSS_GEOMETRY, 500.0, 23.63
    )
    assert live["expected_mpa"] == pytest.approx(45.06, abs=0.2)
    assert live["ratio"] == pytest.approx(0.524, abs=0.02)
    assert live["divergence_flag"] is False
    assert live["band"] == [0.33, 3.0]

    hot = estimate.expected_vs_actual("brake_pedal", XTRUSS_GEOMETRY, 500.0, 300.0)
    assert hot["ratio"] > 3.0 and hot["divergence_flag"] is True

    cold = estimate.expected_vs_actual("brake_pedal", XTRUSS_GEOMETRY, 500.0, 2.0)
    assert cold["ratio"] < 0.33 and cold["divergence_flag"] is True


def test_caveat_present_for_lattice_absent_for_solid():
    lattice = estimate.expected_vs_actual(
        "brake_pedal", XTRUSS_GEOMETRY, 500.0, 23.63
    )
    assert "solid section" in lattice["caveat"]
    solid = estimate.expected_vs_actual("brake_pedal", SOLID_GEOMETRY, 500.0, 23.63)
    assert "caveat" not in solid


def test_missing_actual_keeps_expected_without_flag():
    out = estimate.expected_vs_actual("brake_pedal", XTRUSS_GEOMETRY, 500.0, None)
    assert out["expected_mpa"] == pytest.approx(45.06, abs=0.2)
    assert out["actual_mpa"] is None
    assert out["ratio"] is None
    assert out["divergence_flag"] is None


def test_unknown_part_returns_none():
    assert estimate.expected_vs_actual("warp_drive", {}, 100.0, 50.0) is None


def test_cantilever_expected_vs_actual_block():
    out = estimate.expected_vs_actual(
        "cantilever",
        {"length_mm": 100.0, "width_mm": 20.0, "height_mm": 5.0},
        100.0,
        120.0,
    )
    assert out["expected_mpa"] == pytest.approx(120.0, abs=0.01)
    assert out["ratio"] == pytest.approx(1.0, abs=0.01)
    assert out["divergence_flag"] is False
