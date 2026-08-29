"""
VayuSutra APIx - Policy What-if Scenario Simulator Routers
"""
from fastapi import APIRouter, HTTPException
from ...api.schemas import ScenarioInputModel
from ...scenario.simulator import ScenarioInput, run_scenario_from_db

router = APIRouter(prefix="/api/v1/scenario", tags=["Scenario"])


@router.post("/simulate", summary="Run a policy what-if scenario")
def simulate(input: ScenarioInputModel):
    si = ScenarioInput(
        airfare_shock_pct=input.airfare_shock_pct,
        demand_change_pct=input.demand_change_pct,
        capacity_change_pct=input.capacity_change_pct,
        atf_adjustment_pct=input.atf_adjustment_pct,
        booking_horizon_shock_pct=input.booking_horizon_shock_pct,
        seasonal_factor_pct=input.seasonal_factor_pct,
        name=input.name,
    )
    try:
        return run_scenario_from_db(si).to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", summary="Past scenario runs")
def scenario_history(limit: int = 20):
    from ...config.db import get_db_connection
    import json
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM scenario_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r["id"], "name": r["scenario_name"], "params": json.loads(r["params_json"]),
             "pressure_score": r["pressure_score"], "pressure_level": r["pressure_level"],
             "projected_cpi_bps": r["projected_cpi_bps"], "data_status": r["data_status"],
             "created_at": r["created_at"]} for r in rows]
