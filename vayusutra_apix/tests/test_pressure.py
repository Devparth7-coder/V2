"""Tests for the Airfare Inflation Pressure Score."""
import pytest

from vayusutra_apix.analytics.pressure import (
    PressureComponents, PressureEngine, DEFAULT_PRESSURE_WEIGHTS, _level_for,
)


def test_weights_sum_to_one():
    assert abs(sum(DEFAULT_PRESSURE_WEIGHTS.values()) - 1.0) < 1e-6


def test_zero_components_give_low_score():
    report = PressureEngine().compute(PressureComponents())
    assert report.score <= 25
    assert report.level == "LOW"


def test_high_components_give_high_score():
    comps = PressureComponents(
        airfare_acceleration=3.0, route_breadth=0.9, t1_pressure=3.0,
        t7_pressure=2.0, volatility=2.0, forecast_acceleration=3.0, cpi_transmission=2.0,
    )
    report = PressureEngine().compute(comps)
    assert report.score > 50
    assert report.level in ("HIGH", "CRITICAL")


def test_score_bounds():
    comps = PressureComponents(airfare_acceleration=100.0, route_breadth=1.0,
                               volatility=100.0, cpi_transmission=100.0)
    report = PressureEngine().compute(comps)
    assert 0 <= report.score <= 100


def test_previous_score_change():
    report = PressureEngine().compute(PressureComponents(airfare_acceleration=1.0), previous_score=50.0)
    assert report.change == pytest.approx(report.score - 50.0)


def test_level_mapping():
    assert _level_for(10) == "LOW"
    assert _level_for(35) == "MODERATE"
    assert _level_for(60) == "HIGH"
    assert _level_for(90) == "CRITICAL"


def test_drivers_present():
    report = PressureEngine().compute(PressureComponents(airfare_acceleration=2.0, route_breadth=0.7))
    assert len(report.drivers) > 0
    assert report.drivers[0]["component"] in report.to_dict()["drivers"][0]["component"]
