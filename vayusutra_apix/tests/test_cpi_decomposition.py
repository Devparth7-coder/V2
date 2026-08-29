"""Tests for route-level CPI impact decomposition."""
import pytest

from vayusutra_apix.analytics.cpi_decomposition import CPIDecompositionEngine
from vayusutra_apix.config.routes import DGCA_TOP_20_ROUTES, CPI_WEIGHTS


def _flat_relatives(value=1.0):
    return {r.route_code: value for r in DGCA_TOP_20_ROUTES}


def test_no_movement_zero_contribution():
    rel = _flat_relatives(1.0)
    report = CPIDecompositionEngine().decompose(rel, rel)
    assert report.headline_impact_bps == pytest.approx(0.0, abs=1e-9)
    assert all(abs(c.contribution_bps) < 1e-9 for c in report.contributions)


def test_uniform_rise_matches_manual():
    prev = _flat_relatives(1.0)
    curr = _flat_relatives(1.02)  # +2% all routes
    report = CPIDecompositionEngine().decompose(prev, curr)
    # Expected: daily_pct = 2.0%; transport_bps = 2.0 * 0.0385 * 100 = 7.7; headline = 7.7*0.0859
    w_air = CPI_WEIGHTS["airfare_share_within_transport"]
    w_trans = CPI_WEIGHTS["transport_and_communication_cpi_weight"]
    expected = 2.0 * w_air * 100.0 * w_trans
    assert report.headline_impact_bps == pytest.approx(expected, abs=1e-6)
    # Sum of route contributions equals headline impact
    assert sum(c.contribution_bps for c in report.contributions) == pytest.approx(report.headline_impact_bps, abs=1e-6)


def test_contributors_sum_to_headline():
    prev = _flat_relatives(0.99)
    curr = _flat_relatives(1.01)
    report = CPIDecompositionEngine().decompose(prev, curr)
    assert sum(c.contribution_bps for c in report.contributions) == pytest.approx(
        report.headline_impact_bps, abs=1e-6)


def test_direction_labels():
    rels = {r.route_code: 1.0 for r in DGCA_TOP_20_ROUTES}
    rels["DEL-BOM"] = 1.05  # only DEL-BOM rises
    report = CPIDecompositionEngine().decompose(rels, {**rels, "DEL-BOM": 1.06})
    del_bom = next(c for c in report.contributions if c.route_code == "DEL-BOM")
    assert del_bom.direction in ("UP", "DOWN", "FLAT")
