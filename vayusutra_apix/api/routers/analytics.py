"""
VayuSutra APIx - Analytics Routers
Heatmap, pressure score, CPI decomposition, source consensus, source analytics,
route intelligence and comparison, and the India route map.
"""
import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query

from ...config.routes import ROUTE_LOOKUP, DGCA_TOP_20_ROUTES
from ...services.cache import api_cache
from ...services.india_map import CITY_NAMES

router = APIRouter(prefix="/api/v1", tags=["Analytics"])


@router.get("/analytics/heatmap", summary="Airfare Heatmap (20 routes x 5 horizons)")
def get_heatmap():
    from ...analytics.heatmap import build_heatmap_from_db
    key = f"heatmap-{datetime.date.today().isoformat()}"
    data = api_cache.get_or_compute(key, lambda: build_heatmap_from_db().to_dict(), ttl_seconds=60)
    return data


@router.get("/analytics/pressure", summary="Airfare Inflation Pressure Score")
def get_pressure():
    from ...analytics.pressure import compute_pressure_from_db
    key = f"pressure-{datetime.date.today().isoformat()}"
    prev = api_cache.get("pressure-prev")
    data = api_cache.get_or_compute(key, lambda: compute_pressure_from_db(previous_score=prev).to_dict(),
                                    ttl_seconds=60)
    api_cache.set("pressure-prev", data["pressure_score"], ttl_seconds=3600)
    return data


@router.get("/analytics/cpi-decomposition", summary="Route-level CPI Impact Decomposition")
def get_cpi_decomposition():
    from ...analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    key = f"cpi-dec-{datetime.date.today().isoformat()}"
    return api_cache.get_or_compute(key, lambda: compute_cpi_decomposition_from_db().to_dict(), ttl_seconds=60)


@router.get("/analytics/source-consensus", summary="Source Consensus & Disagreement")
def get_source_consensus(route_code: Optional[str] = Query(None),
                         advance_window: Optional[str] = Query(None)):
    from ...analytics.consensus import compute_source_consensus_from_db
    results = compute_source_consensus_from_db(route_code=route_code, advance_window=advance_window)
    return {"count": len(results), "data": [r.to_dict() for r in results]}


@router.get("/analytics/source-analytics", summary="Airline / OTA / Route / Horizon Analytics")
def get_source_analytics():
    from ...analytics.source_analytics import build_source_analytics_from_db
    return build_source_analytics_from_db()


@router.get("/analytics/route/{route_code}", summary="Route Intelligence")
def get_route_intelligence(route_code: str,
                           include_forecast: bool = Query(True),
                           include_anomalies: bool = Query(True)):
    if ROUTE_LOOKUP.get(route_code.upper()) is None:
        raise HTTPException(status_code=404, detail=f"Route {route_code} not in DGCA Top-20 basket.")
    from ...analytics.route_intelligence import build_route_intelligence_from_db
    return build_route_intelligence_from_db(route_code, include_forecast=include_forecast,
                                            include_anomalies=include_anomalies)


@router.get("/analytics/compare", summary="Compare multiple routes")
def compare_routes(route_codes: str = Query(..., description="Comma-separated route codes, e.g. DEL-BOM,DEL-BLR,BOM-DEL")):
    codes = [c.strip().upper() for c in route_codes.split(",") if c.strip()]
    if len(codes) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two route codes.")
    from ...analytics.route_intelligence import build_route_intelligence_from_db
    results = []
    for code in codes:
        if ROUTE_LOOKUP.get(code) is None:
            raise HTTPException(status_code=404, detail=f"Route {code} not in basket.")
        try:
            results.append(build_route_intelligence_from_db(code, include_forecast=False,
                                                             include_anomalies=False))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"count": len(results), "comparison": results}


@router.get("/analytics/route-map", summary="India route map segments")
def get_route_map():
    from ...services.india_map import route_segments
    return {"segments": route_segments(), "airports": {c: {"name": n} for c, n in CITY_NAMES.items()}}


@router.get("/analytics/overview", summary="National intelligence overview (KPI cards + context)")
def get_overview():
    """Aggregated snapshot for the command-center dashboard (one call)."""
    from ...config.db import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    prev = conn.execute("SELECT laspeyres_index FROM national_indices "
                        "WHERE calculation_date < (SELECT MAX(calculation_date) FROM national_indices) "
                        "ORDER BY calculation_date DESC LIMIT 1").fetchone()
    # 7-day change
    seven = conn.execute("""
        SELECT laspeyres_index FROM national_indices
        ORDER BY calculation_date DESC LIMIT 7
    """).fetchall()
    seven_change = None
    if seven and len(seven) >= 2:
        seven_change = ((seven[0]["laspeyres_index"] - seven[-1]["laspeyres_index"])
                        / seven[-1]["laspeyres_index"] * 100.0) if seven[-1]["laspeyres_index"] else 0.0

    from ...analytics.pressure import compute_pressure_from_db
    from ...data_quality.trust import compute_trust_report_from_db
    from ...anomaly.detector import get_anomalies_from_db
    from ...forecasting.service import get_national_forecast
    from ...analytics.heatmap import build_heatmap_from_db

    pressure = compute_pressure_from_db()
    dq = compute_trust_report_from_db()
    anomalies = get_anomalies_from_db(limit=5)
    heat = build_heatmap_from_db()
    forecast = None
    try:
        fc = get_national_forecast(7)
        forecast = fc.to_dict()
    except Exception:
        forecast = None

    raw_cnt = conn.execute("SELECT COUNT(*) c FROM raw_quotes").fetchone()["c"]
    clean_cnt = conn.execute("SELECT COUNT(*) c FROM cleaned_quotes WHERE outlier_flag=0").fetchone()["c"]
    active_routes = conn.execute("SELECT COUNT(DISTINCT route_code) c FROM route_indices").fetchone()["c"]

    return {
        "as_of": row["calculation_date"] if row else None,
        "data_status": "SIMULATED",
        "kpi": {
            "national_airfare_index": row["laspeyres_index"] if row else None,
            "daily_change_pct": row["daily_pct_change"] if row else 0.0,
            "seven_day_change_pct": round(seven_change, 3) if seven_change is not None else None,
            "cpi_contribution_bps": row["bps_headline_cpi_impact"] if row else 0.0,
            "market_pressure_score": pressure.score,
            "market_pressure_level": pressure.level,
            "data_trust_score": dq.trust_score,
            "active_routes": active_routes,
            "quotes_processed": clean_cnt,
            "raw_quotes_ingested": raw_cnt,
            "last_update": row["calculation_date"] if row else None,
        },
        "pressure": pressure.to_dict(),
        "data_quality": dq.to_dict(),
        "anomalies": anomalies,
        "forecast_7d": forecast,
        "heatmap": heat.to_dict(),
        "top_risers": _top_risers(conn, 5),
        "top_fallers": _top_fallers(conn, 5),
    }


def _top_risers(conn, n):
    from ...analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    dec = compute_cpi_decomposition_from_db()
    up = sorted([c for c in dec.contributions if c.contribution_bps >= 0],
                key=lambda c: c.contribution_bps, reverse=True)[:n]
    return [c.to_dict() for c in up]


def _top_fallers(conn, n):
    from ...analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    dec = compute_cpi_decomposition_from_db()
    down = sorted([c for c in dec.contributions if c.contribution_bps < 0],
                  key=lambda c: c.contribution_bps)[:n]
    return [c.to_dict() for c in down]


