"""Tests for the Data Trust Center scoring."""
import pytest

from vayusutra_apix.data_quality.trust import DataTrustCalculator, DEFAULT_COMPONENT_WEIGHTS


def test_weights_sum_to_one():
    assert abs(sum(DEFAULT_COMPONENT_WEIGHTS.values()) - 1.0) < 1e-6


def test_perfect_inputs_give_high_score():
    calc = DataTrustCalculator()
    report = calc.compute(age_days=0, present_cells=100, total_cells=100,
                          routes_present=20, total_routes=20, sources_seen=7,
                          total_sources=7, duplicate_rate=0.0, outlier_rate=0.0,
                          validation_score=100.0, source_agreement=100.0)
    assert report.trust_score >= 85
    assert report.level == "EXCELLENT"


def test_stale_and_incomplete_lower_score():
    calc = DataTrustCalculator()
    report = calc.compute(age_days=20, present_cells=50, total_cells=100,
                          routes_present=10, total_routes=20, sources_seen=2,
                          total_sources=7, duplicate_rate=30.0, outlier_rate=20.0,
                          validation_score=40.0, source_agreement=30.0)
    assert report.trust_score < 50
    assert report.level == "POOR"


def test_score_bounds():
    calc = DataTrustCalculator()
    r = calc.compute(age_days=None, present_cells=0, total_cells=100, routes_present=0,
                     total_routes=20, sources_seen=0, total_sources=7, duplicate_rate=99,
                     outlier_rate=99, validation_score=0, source_agreement=0)
    assert 0 <= r.trust_score <= 100


def test_duplicate_rate_reported():
    calc = DataTrustCalculator()
    r = calc.compute(age_days=1, present_cells=100, total_cells=100, routes_present=20,
                     total_routes=20, sources_seen=7, total_sources=7, duplicate_rate=1.2,
                     outlier_rate=2.8, validation_score=100, source_agreement=90)
    assert r.components.duplicate_rate == pytest.approx(1.2)
    assert r.components.outlier_rate == pytest.approx(2.8)
