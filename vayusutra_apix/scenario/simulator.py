"""
VayuSutra APIx - Policy What-if Scenario Simulator
Allows a policy analyst to perturb market fundamentals (airfare shock, demand, capacity,
ATF, booking-horizon, seasonality) and see the projected index, CPI impact and pressure.
All results are MODELLED / SIMULATED — they are never presented as actual forecasts.

The transmission model is transparent and documented:
  projected_index_change = airfare_shock
                         + demand_price_effect      (demand_change / |elasticity|)
                         + capacity_price_effect    (-capacity_change * supply_pass_through)
                         + atf_fuel_pass_through    (atf_adjustment * fuel_share)
                         + horizon_shock_effect
                         + seasonal_effect
"""
import datetime
import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from ..config.routes import DGCA_TOP_20_ROUTES, CPI_WEIGHTS
from ..config.db import get_db_connection

DEMAND_ELASTICITY = -0.85
SUPPLY_PASS_THROUGH = 0.50
FUEL_SHARE = 0.35
HORIZON_SHOCK_PASS = 0.10
SEASONAL_PASS = 0.50


@dataclass
class ScenarioInput:
    airfare_shock_pct: float = 0.0
    demand_change_pct: float = 0.0
    capacity_change_pct: float = 0.0
    atf_adjustment_pct: float = 0.0
    booking_horizon_shock_pct: float = 0.0
    seasonal_factor_pct: float = 0.0
    name: str = "Custom scenario"

    def to_dict(self) -> Dict[str, float]:
        return {
            "airfare_shock_pct": self.airfare_shock_pct,
            "demand_change_pct": self.demand_change_pct,
            "capacity_change_pct": self.capacity_change_pct,
            "atf_adjustment_pct": self.atf_adjustment_pct,
            "booking_horizon_shock_pct": self.booking_horizon_shock_pct,
            "seasonal_factor_pct": self.seasonal_factor_pct,
        }


@dataclass
class ScenarioResult:
    scenario_name: str
    inputs: ScenarioInput
    current_index: float
    projected_index: float
    index_change_pct: float
    transport_impact_bps: float
    headline_cpi_impact_bps: float
    pressure_level: str
    pressure_score: float
    route_impacts: List[Dict[str, Any]]
    confidence_range: Dict[str, float]
    data_status: str = "MODELLED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "inputs": self.inputs.to_dict(),
            "current_index": round(self.current_index, 2),
            "projected_index": round(self.projected_index, 2),
            "projected_index_change_pct": round(self.index_change_pct, 2),
            "projected_transport_cpi_bps": round(self.transport_impact_bps, 4),
            "projected_headline_cpi_bps": round(self.headline_cpi_impact_bps, 4),
            "pressure": {"score": round(self.pressure_score, 1), "level": self.pressure_level},
            "route_level_impact": self.route_impacts,
            "confidence_range": self.confidence_range,
            "data_status": self.data_status,
            "modelled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


class PolicySimulator:
    def __init__(self, base_index: float = 100.0):
        self.base_index = base_index

    def simulate(self, inputs: ScenarioInput) -> ScenarioResult:
        inp = inputs
        demand_effect = inp.demand_change_pct / abs(DEMAND_ELASTICITY) if DEMAND_ELASTICITY != 0 else 0.0
        capacity_effect = -inp.capacity_change_pct * SUPPLY_PASS_THROUGH
        atf_effect = inp.atf_adjustment_pct * FUEL_SHARE
        horizon_effect = inp.booking_horizon_shock_pct * HORIZON_SHOCK_PASS
        seasonal_effect = inp.seasonal_factor_pct * SEASONAL_PASS

        total_pct = (inp.airfare_shock_pct + demand_effect + capacity_effect +
                     atf_effect + horizon_effect + seasonal_effect)

        projected_index = self.base_index * (1.0 + total_pct / 100.0)
        index_change_pct = total_pct

        w_air = CPI_WEIGHTS["airfare_share_within_transport"]
        w_trans = CPI_WEIGHTS["transport_and_communication_cpi_weight"]
        transport_bps = index_change_pct * w_air * 100.0
        headline_bps = transport_bps * w_trans

        # Pressure (forecast_acceleration = projected change)
        from ..analytics.pressure import PressureComponents, PressureEngine
        comps = PressureComponents(
            airfare_acceleration=index_change_pct,
            forecast_acceleration=index_change_pct,
            cpi_transmission=headline_bps,
        )
        pressure = PressureEngine().compute(comps)

        # Route-level impact (distribute by weight; larger on higher-weight routes)
        route_impacts = []
        for r in DGCA_TOP_20_ROUTES:
            route_change = index_change_pct * (0.6 + 0.4 * (r.weight / 0.11))
            route_impacts.append({
                "route_code": r.route_code,
                "projected_change_pct": round(route_change, 2),
                "weight": round(r.weight, 4),
            })
        route_impacts.sort(key=lambda x: x["weight"], reverse=True)

        # Confidence range for the modelled projection
        uncertainty = max(2.0, abs(index_change_pct) * 0.25)
        confidence_range = {
            "lower_index": round(projected_index - uncertainty, 2),
            "upper_index": round(projected_index + uncertainty, 2),
            "uncertainty_pct": round(uncertainty / projected_index * 100.0, 2) if projected_index else 0.0,
        }

        return ScenarioResult(
            scenario_name=inp.name, inputs=inp,
            current_index=round(self.base_index, 2),
            projected_index=round(projected_index, 2),
            index_change_pct=round(index_change_pct, 2),
            transport_impact_bps=round(transport_bps, 4),
            headline_cpi_impact_bps=round(headline_bps, 4),
            pressure_level=pressure.level, pressure_score=pressure.score,
            route_impacts=route_impacts, confidence_range=confidence_range,
        )


def run_scenario_from_db(inputs: ScenarioInput) -> ScenarioResult:
    conn = get_db_connection()
    row = conn.execute("SELECT laspeyres_index FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    base = row["laspeyres_index"] if row else 100.0
    result = PolicySimulator(base).simulate(inputs)

    # Persist
    run_id = f"SC-{uuid.uuid4().hex[:10]}"
    with conn:
        conn.execute("""
            INSERT INTO scenario_runs (
                id, scenario_name, params_json, results_json, pressure_score,
                pressure_level, projected_cpi_bps, data_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, result.scenario_name, json.dumps(inputs.to_dict()),
              json.dumps(result.to_dict()), result.pressure_score, result.pressure_level,
              result.headline_cpi_impact_bps, "MODELLED",
              datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return result
