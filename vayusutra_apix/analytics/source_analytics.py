"""
VayuSutra APIx - Airline / Source Analytics
Analytics by airline, OTA, route and booking horizon using actual cleaned quotes only.
Market share is only reported when valid DGCA share data exists in config; otherwise the
output explicitly says "Data unavailable" rather than inventing numbers.
"""
from typing import Dict, List, Any
import numpy as np

from ..config.routes import AIRLINE_MARKET_SHARES, AIRLINE_LOOKUP
from ..config.db import get_db_connection


def build_source_analytics_from_db() -> Dict[str, Any]:
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT c.airline_code, r.source_portal, c.route_code, c.advance_window, c.final_total_fare
        FROM cleaned_quotes c
        LEFT JOIN raw_quotes r ON c.raw_quote_id = r.quote_id
        WHERE c.outlier_flag=0 AND c.final_total_fare>0
    """).fetchall()

    by_airline: Dict[str, List[float]] = {}
    by_ota: Dict[str, List[float]] = {}
    by_route: Dict[str, List[float]] = {}
    by_horizon: Dict[str, List[float]] = {}
    airline_sources: Dict[str, set] = {}

    for r in rows:
        by_airline.setdefault(r["airline_code"], []).append(r["final_total_fare"])
        by_route.setdefault(r["route_code"], []).append(r["final_total_fare"])
        by_horizon.setdefault(r["advance_window"], []).append(r["final_total_fare"])
        portal = str(r["source_portal"])
        if portal.startswith("OTA"):
            by_ota.setdefault(portal, []).append(r["final_total_fare"])
        airline_sources.setdefault(r["airline_code"], set()).add(portal)

    def summarize(vals: List[float]) -> Dict[str, Any]:
        arr = np.array(vals, dtype=float)
        med = float(np.median(arr))
        avg = float(np.mean(arr))
        vol = float(np.std(arr) / med) if med > 0 else 0.0
        return {"samples": len(vals), "median_fare": round(med, 2),
                "average_fare": round(avg, 2), "volatility": round(vol, 4)}

    airlines = []
    for code, vals in by_airline.items():
        share = None
        share_status = "AVAILABLE"
        adef = AIRLINE_LOOKUP.get(code)
        if adef is not None:
            share = adef.market_share
        else:
            share_status = "Data unavailable"  # no official DGCA share for this code
        airlines.append({
            "airline_code": code,
            "airline_name": adef.name if adef else "Unknown",
            **summarize(vals),
            "market_share": share,
            "market_share_status": share_status,
            "source_coverage": len(airline_sources.get(code, set())),
        })

    otas = [{"source_portal": k, **summarize(v)} for k, v in sorted(by_ota.items())]
    routes = [{"route_code": k, **summarize(v)} for k, v in sorted(by_route.items())]
    horizons = [{"advance_window": k, **summarize(v)}
                for k, v in sorted(by_horizon.items(), key=lambda kv: int(kv[0].replace("T+", "")))]

    return {
        "data_status": "SIMULATED",
        "airlines": airlines,
        "otas": otas,
        "routes": routes,
        "booking_horizons": horizons,
        "market_share_note": "Market share reported only where official DGCA share exists; otherwise 'Data unavailable'.",
    }
