"""Tests for the policy what-if scenario simulator."""
import pytest

from vayusutra_apix.scenario.simulator import PolicySimulator, ScenarioInput


def test_zero_input_no_change():
    sim = PolicySimulator(base_index=105.0)
    r = sim.simulate(ScenarioInput())
    assert r.projected_index == pytest.approx(105.0)
    assert r.index_change_pct == pytest.approx(0.0)


def test_positive_shock_raises_index_and_pressure():
    sim = PolicySimulator(base_index=105.0)
    r = sim.simulate(ScenarioInput(airfare_shock_pct=10.0))
    assert r.projected_index > 105.0
    assert r.index_change_pct == pytest.approx(10.0)
    assert r.headline_cpi_impact_bps > 0
    assert r.pressure_score > 25


def test_negative_shock_lowers_index():
    sim = PolicySimulator(base_index=105.0)
    r = sim.simulate(ScenarioInput(airfare_shock_pct=-10.0))
    assert r.projected_index < 105.0
    assert r.headline_cpi_impact_bps < 0


def test_demand_and_capacity_effects():
    sim = PolicySimulator(base_index=100.0)
    # +demand => price up; -capacity => price up
    r = sim.simulate(ScenarioInput(demand_change_pct=5.0, capacity_change_pct=-3.0))
    assert r.index_change_pct > 0


def test_modelled_label():
    sim = PolicySimulator(base_index=100.0)
    r = sim.simulate(ScenarioInput(airfare_shock_pct=5.0))
    assert r.data_status == "MODELLED"


def test_route_impacts_present():
    sim = PolicySimulator(base_index=100.0)
    r = sim.simulate(ScenarioInput(airfare_shock_pct=10.0))
    assert len(r.route_impacts) == 20
    assert r.route_impacts[0]["route_code"]  # sorted by weight
