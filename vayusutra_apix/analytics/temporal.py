"""
VayuSutra APIx - Advanced Temporal Analytics
Weekday/weekend patterns, booking-horizon distribution, route-level and seasonal movement.
Patterns are reported descriptively; statistical significance is only claimed when a
one-sample t-test on weekday deviations passes (p<0.05), otherwise it says 'not significant'.
"""
import datetime
from typing import Dict, List, Any
import numpy as np

from ..config.routes import ADVANCE_PURCHASE_WINDOWS
from ..config.db import get_db_connection


def _weekday_analysis(conn) -> Dict[str, Any]:
    rows = conn.execute("""
        SELECT calculation_date, daily_pct_change FROM national_indices
        WHERE daily_pct_change IS NOT NULL ORDER BY calculation_date ASC
    """).fetchall()
    if len(rows) < 7:
        return {"data": [], "significance": "insufficient data"}
    import scipy.stats as st
    groups: Dict[str, List[float]] = {i: [] for i in range(7)}
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for r in rows:
        try:
            dow = datetime.date.fromisoformat(r["calculation_date"]).weekday()
            groups[dow].append(r["daily_pct_change"])
        except Exception:
            continue
    out = []
    overall = np.array([r["daily_pct_change"] for r in rows])
    for i in range(7):
        vals = np.array(groups[i], dtype=float)
        mean = float(np.mean(vals)) if len(vals) else 0.0
        sig = False
        if len(vals) >= 3 and np.std(vals) > 0:
            t, p = st.ttest_1samp(vals, float(np.mean(overall)))
            sig = bool(p < 0.05)
        out.append({"weekday": names[i], "avg_daily_change_pct": round(mean, 4),
                    "samples": len(vals), "significant": sig,
                    "note": "not significant" if not sig else "statistically significant (p<0.05)"})
    return {"data": out, "significance": "computed"}


def _horizon_distribution(conn) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT advance_window, AVG(price_relative) rel, COUNT(*) n
        FROM route_indices GROUP BY advance_window
    """).fetchall()
    rel = {r["advance_window"]: r["rel"] for r in rows}
    n = {r["advance_window"]: r["n"] for r in rows}
    out = []
    for w in ADVANCE_PURCHASE_WINDOWS:
        out.append({"window_id": w.window_id, "days_advance": w.days_advance,
                    "avg_price_relative": round(rel.get(w.window_id, 1.0), 4),
                    "samples": n.get(w.window_id, 0)})
    return out


def _route_temporal(conn) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT route_code, COUNT(DISTINCT calculation_date) days, AVG(price_relative) avg_rel
        FROM route_indices GROUP BY route_code
    """).fetchall()
    return [{"route_code": r["route_code"], "days_observed": r["days"],
             "avg_price_relative": round(r["avg_rel"], 4)} for r in rows]


def build_temporal_analytics_from_db() -> Dict[str, Any]:
    conn = get_db_connection()
    return {
        "weekday_analysis": _weekday_analysis(conn),
        "booking_horizon_distribution": _horizon_distribution(conn),
        "route_temporal_profile": _route_temporal(conn),
        "data_status": "SIMULATED",
        "note": "Statistical significance reported only where a t-test passes p<0.05.",
    }
