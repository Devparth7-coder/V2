"""
VayuSutra APIx - Econometric Mathematical Formula Tests
Numerically verifies Jevons Geometric Mean, Laspeyres, Paasche, Fisher Ideal Index,
and CPI Basis Point (bps) Transmission Formulations against analytical proofs.
"""

import math
import pytest
from vayusutra_apix.engine.index_calculator import IndexCalculationEngine
from vayusutra_apix.config.routes import CPI_WEIGHTS


def test_jevons_geometric_mean_analytical():
    """Verify Jevons geometric mean: prod(x_i)^(1/n) = exp(1/n * sum ln(x_i))."""
    # For [100, 200, 400], prod is 8,000,000; cube root is 200.0
    fares = [100.0, 200.0, 400.0]
    result = IndexCalculationEngine.calculate_jevons_geometric_mean(fares)
    assert result == pytest.approx(200.0, rel=1e-5)


def test_laspeyres_and_fisher_math():
    """Verify Laspeyres and Fisher formula mechanics."""
    calc = IndexCalculationEngine()

    # Create synthetic elementary results for 20 routes
    elementary_results = []
    relatives_map = {}
    for r in calc.routes:
        relatives_map[r.route_code] = {}
        for w in calc.windows:
            # 5% constant inflation across all cells
            relatives_map[r.route_code][w.window_id] = 1.05

    nat = calc.compute_national_indices(
        elementary_results=[],
        relatives_map=relatives_map,
        calculation_date="2026-08-26",
        previous_laspeyres_index=100.0,
        total_quotes=1000,
        valid_quotes=980,
        outliers_count=20
    )

    # Laspeyres should be exactly 105.00
    assert nat.laspeyres_index == pytest.approx(105.00, rel=1e-3)
    # Fisher should also be 105.00 when uniform inflation occurs
    assert nat.fisher_index == pytest.approx(105.00, rel=1e-3)
    # Daily pct change from 100.0 to 105.0 should be +5.0%
    assert nat.daily_pct_change == pytest.approx(5.00, rel=1e-3)


def test_cpi_bps_transmission():
    """
    Verify Inflation Transmission:
    Delta % = +10.0%
    Delta Bps Transport = 10.0 * 0.0385 * 100 = 38.5 bps
    Delta Bps Headline = 38.5 * 0.0859 = 3.30715 bps
    """
    w_airfare = CPI_WEIGHTS["airfare_share_within_transport"]  # 0.0385
    w_transport = CPI_WEIGHTS["transport_and_communication_cpi_weight"]  # 0.0859

    delta_pct = 10.0
    bps_transport = delta_pct * w_airfare * 100.0
    bps_headline = bps_transport * w_transport

    assert bps_transport == pytest.approx(38.50, rel=1e-4)
    assert bps_headline == pytest.approx(3.30715, rel=1e-4)


def test_paasche_demand_elasticity():
    """Verify Paasche substitution property: when prices rise, Paasche <= Laspeyres."""
    calc = IndexCalculationEngine()
    relatives_map = {}

    # Asymmetric price increases (some routes +30%, others unchanged)
    for idx, r in enumerate(calc.routes):
        relatives_map[r.route_code] = {}
        for w in calc.windows:
            relatives_map[r.route_code][w.window_id] = 1.30 if idx % 2 == 0 else 1.00

    nat = calc.compute_national_indices(
        elementary_results=[],
        relatives_map=relatives_map,
        calculation_date="2026-08-26",
        previous_laspeyres_index=100.0
    )

    # With negative elasticity (substitution away from expensive routes),
    # Paasche index must be less than or equal to Laspeyres index
    assert nat.paasche_index <= nat.laspeyres_index + 1e-4
    # Fisher must lie between Laspeyres and Paasche
    assert nat.paasche_index <= nat.fisher_index <= nat.laspeyres_index + 1e-4
