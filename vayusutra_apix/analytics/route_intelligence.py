"""
VayuSutra APIx - Route Intelligence
Comprehensive, deterministic per-route analytics assembled from SQLite, used by the
route intelligence pages and route comparison. Includes provenance/lineage pointers.
"""
import datetime
from typing import Dict, List, Any, Optional
import numpy as np

from ..config.routes import DGCA_TOP_20_ROUTES, ROUTE_LOOKUP, BASE_PERIOD_BENCHMARKS
from ..config.db import get_db_connection


def _route_series(conn, route_code: str) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT calculation_date, AVG(price_relative) AS relative, AVG(jevons_mean_fare) AS jevons
        FROM route_indices
        WHERE route_code=? AND jevons_mean_fare > 0
        GROUP BY calculation_date ORDER BY calculation_date ASC
    """, (route_code,)).fetchall()
    return [{"date": r["calculation_date"], "relative": r["relative"], "jevons": r["jevons"]} for r in rows]


def _horizon_fares(conn, route_code: str, calc_date: str) -> Dict[str, Any]:
    rows = conn.execute("""
        SELECT advance_window, jevons_mean_fare, price_relative
        FROM route_indices WHERE route_code=? AND calculation_date=?
    """, (route_code, calc_date)).fetchall()
    return {
        r["advance_window"]: {"fare": r["jevons_mean_fare"], "relative": r["price_relative"]}
        for r in rows
    }


def build_route_intelligence_from_db(route_code: str, include_forecast: bool = True,
                                     include_anomalies: bool = True) -> Dict[str, Any]:
    conn = get_db_connection()
    route_def = ROUTE_LOOKUP.get(route_code.upper())
    if route_def is None:
        raise KeyError(f"Route {route_code} not in DGCA Top-20 basket.")

    series = _route_series(conn, route_def.route_code)
    latest_dt = conn.execute("SELECT MAX(calculation_date) dt FROM route_indices").fetchone()["dt"]
    horizons = _horizon_fares(conn, route_def.route_code, latest_dt) if latest_dt else {}

    # Composite relative as latest per-date average of window relatives (weighted)
    def composite_for(series_idx: int) -> float:
        if series_idx < 0 or series_idx >= len(series):
            return 1.0
        return float(series[series_idx]["relative"])

    comp_now = composite_for(len(series) - 1)
    comp_1 = composite_for(len(series) - 2)
    comp_7 = composite_for(len(series) - 8)
    comp_30 = composite_for(len(series) - 31)

    def pct(a: float, b: float) -> float:
        return ((a - b) / b * 100.0) if b and b > 0 else 0.0

    rels = [s["relative"] for s in series if s["relative"]]
    volatility = float(np.std(rels) / np.mean(rels)) if len(rels) > 1 and np.mean(rels) > 0 else 0.0

    # Median fare from cleaned quotes
    med_row = conn.execute("""
        SELECT AVG(final_total_fare) FROM (
            SELECT final_total_fare FROM cleaned_quotes
            WHERE route_code=? AND outlier_flag=0 AND final_total_fare>0
            ORDER BY final_total_fare LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM cleaned_quotes WHERE route_code=? AND outlier_flag=0 AND final_total_fare>0)
        )
    """, (route_def.route_code, route_def.route_code)).fetchone()
    median_fare = float(med_row[0]) if med_row and med_row[0] else 0.0

    # Airline/source comparison (per-airline median)
    airline_rows = conn.execute("""
        SELECT airline_code, AVG(final_total_fare) AS avg_fare, COUNT(*) AS n
        FROM cleaned_quotes WHERE route_code=? AND outlier_flag=0 AND final_total_fare>0
        GROUP BY airline_code ORDER BY n DESC
    """, (route_def.route_code,)).fetchall()
    airlines = [
        {"airline_code": r["airline_code"], "avg_fare": round(r["avg_fare"], 2), "samples": r["n"]}
        for r in airline_rows
    ]

    # Source consensus for the route
    from .consensus import ConsensusEngine
    consensus_rows = conn.execute("""
        SELECT r.source_portal, c.final_total_fare FROM cleaned_quotes c
        LEFT JOIN raw_quotes r ON c.raw_quote_id = r.quote_id
        WHERE c.route_code=? AND c.outlier_flag=0 AND c.final_total_fare>0
    """, (route_def.route_code,)).fetchall()
    consensus = ConsensusEngine().classify(
        [{"source": r["source_portal"], "fare": r["final_total_fare"]} for r in consensus_rows]
    ).to_dict()

    # CPI contribution for the route
    cpi_contribution = None
    try:
        from .cpi_decomposition import compute_cpi_decomposition_from_db
        dec = compute_cpi_decomposition_from_db()
        for c in dec.contributions:
            if c.route_code == route_def.route_code:
                cpi_contribution = {"contribution_bps": c.contribution_bps,
                                    "price_movement_pct": c.price_movement_pct}
                break
    except Exception:
        cpi_contribution = None

    # Forecast (optional)
    forecast = None
    if include_forecast:
        try:
            from ..forecasting.service import get_route_forecast
            f = get_route_forecast(route_def.route_code)
            forecast = {
                "horizon_days": f.horizon_days, "model": f.model,
                "point_forecast": round(f.point_forecast, 2),
                "lower_bound": round(f.lower_bound, 2), "upper_bound": round(f.upper_bound, 2),
                "confidence_level": f.confidence_level, "generated_at": f.generated_at,
            }
        except Exception:
            forecast = None

    # Anomaly history (optional)
    anomaly_history = []
    if include_anomalies:
        try:
            an_rows = conn.execute("""
                SELECT anomaly_type, severity, severity_score, timestamp, observed_value,
                       expected_lower, expected_upper, explanation
                FROM anomalies WHERE route_code=? ORDER BY detected_at DESC LIMIT 10
            """, (route_def.route_code,)).fetchall()
            anomaly_history = [dict(r) for r in an_rows]
        except Exception:
            anomaly_history = []

    representative_jevons = round(route_def.base_fare_benchmark * comp_now, 2) if comp_now else 0.0

    return {
        "route_code": route_def.route_code,
        "origin_city": route_def.origin_city,
        "destination_city": route_def.destination_city,
        "distance_km": route_def.distance_km,
        "dgca_weight": route_def.weight,
        "as_of_date": latest_dt,
        "current_median_fare_inr": round(median_fare, 2),
        "representative_jevons_fare_inr": representative_jevons,
        "index_relative": round(comp_now, 4),
        "changes": {
            "24h_pct": round(pct(comp_now, comp_1), 2),
            "7d_pct": round(pct(comp_now, comp_7), 2),
            "30d_pct": round(pct(comp_now, comp_30), 2),
        },
        "volatility": round(volatility, 4),
        "horizons": {k: {"fare": round(v["fare"], 2), "relative": round(v["relative"], 4)}
                     for k, v in horizons.items()},
        "source_consensus": consensus,
        "airlines": airlines,
        "cpi_contribution_bps": round(cpi_contribution["contribution_bps"], 4) if cpi_contribution else None,
        "historical": series[-60:],
        "forecast": forecast,
        "anomaly_history": anomaly_history,
        "provenance": {
            "route_data_source": "route_indices table (SIMULATED)",
            "quote_data_source": "cleaned_quotes table (SIMULATED)",
            "traceable_quotes": True,
        },
    }
