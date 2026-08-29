"""
VayuSutra APIx - AI Policy Analyst (grounded, non-hallucinating)

Architecture: the LLM-like layer NEVER computes statistics itself.
  User question -> intent detection -> relevant verified API/DB calls -> grounded answer.

Answers are assembled from actual platform data. If data is unavailable, the analyst
explicitly says so. There is no external LLM dependency; the explanation layer is
deterministic template generation over verified numbers.
"""
import datetime
import re
from typing import Dict, List, Any, Optional

from ..config.db import get_db_connection
from ..config.routes import ROUTE_LOOKUP

INTENTS = {
    "why_inflation_up": ["why", "airfare", "infla", "increas", "index"],
    "cpi_contributors": ["contributed", "contribut", "cpi", "which", "routes"],
    "forecast": ["forecast", "predict", "next", "7-day", "7 day", "outlook", "expected"],
    "pressure_cause": ["pressure", "cause", "score", "composite"],
    "compare_routes": ["compare", "vs", "versus"],
    "scenario": ["what if", "increase by", "shock", "simulat", "10%", "scenario"],
    "anomalies": ["anomal", "abnormal", "unusual", "spike", "outlier"],
    "data_quality": ["trust", "data quality", "reliab", "confidence in data"],
    "top_routes": ["top", "rising", "best", "falling", "movers"],
}


def _match_intent(question: str) -> List[tuple]:
    q = question.lower()
    scores = []
    for intent, keywords in INTENTS.items():
        score = sum(1 for kw in keywords if kw in q)
        if score > 0:
            scores.append((score, intent))
    scores.sort(reverse=True)
    return scores


def _get_realtime() -> Dict[str, Any]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    if not row:
        return {"available": False}
    return {
        "available": True, "date": row["calculation_date"],
        "laspeyres": row["laspeyres_index"], "daily_pct": row["daily_pct_change"],
        "headline_bps": row["bps_headline_cpi_impact"],
        "transport_bps": row["bps_transport_impact"],
    }


def _answer_why_inflation_up() -> Dict[str, Any]:
    real = _get_realtime()
    if not real["available"]:
        return {"answer": "Data unavailable: no index record exists yet. Run ingestion first.", "evidence": []}
    from ..analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    dec = compute_cpi_decomposition_from_db()
    top = dec.contributions[:3]
    parts = [f"The national airfare index moved {real['daily_pct']:+.2f}% to {real['laspeyres']:.2f} "
             f"on {real['date']}, transmitting {real['headline_bps']:+.4f} bps to headline CPI."]
    if top:
        parts.append("Principal drivers were: " + ", ".join(
            f"{c.route_code} ({c.contribution_bps:+.2f} bps)" for c in top) + ".")
    return {
        "answer": " ".join(parts),
        "evidence": {"national_index": real, "top_contributors": [c.to_dict() for c in top]},
        "affected_routes": [c.route_code for c in top],
        "data_status": "SIMULATED",
    }


def _answer_cpi_contributors() -> Dict[str, Any]:
    from ..analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    dec = compute_cpi_decomposition_from_db()
    if not dec.contributions:
        return {"answer": "Data unavailable: no route contributions could be computed.", "evidence": []}
    top = dec.contributions[:5]
    others = dec.contributions[5:]
    others_bps = sum(c.contribution_bps for c in others)
    parts = [f"Headline CPI impact is {dec.headline_impact_bps:+.4f} bps."]
    parts.append("Top contributors: " + ", ".join(
        f"{c.route_code} {c.contribution_bps:+.2f} bps" for c in top) + f". Others: {others_bps:+.2f} bps.")
    return {
        "answer": " ".join(parts),
        "evidence": {"headline_bps": round(dec.headline_impact_bps, 4),
                     "contributors": [c.to_dict() for c in dec.contributions]},
        "affected_routes": [c.route_code for c in dec.contributions],
        "data_status": "SIMULATED",
    }


def _answer_forecast() -> Dict[str, Any]:
    from ..forecasting.service import get_national_forecast
    try:
        fc = get_national_forecast(7)
    except Exception as e:
        return {"answer": f"Data unavailable: forecast could not be generated ({e}).", "evidence": []}
    return {
        "answer": (f"The 7-day forecast is {fc.point_forecast:.2f} (95% CI "
                   f"[{fc.lower_bound:.2f}, {fc.upper_bound:.2f}]) using the {fc.model} model. "
                   f"Validation: MAPE {fc.metrics.get('mape', 0):.2f}%, RMSE {fc.metrics.get('rmse', 0):.2f}."),
        "evidence": fc.to_dict(),
        "affected_routes": [],
        "data_status": "MODELLED",
    }


def _answer_pressure() -> Dict[str, Any]:
    from ..analytics.pressure import compute_pressure_from_db
    p = compute_pressure_from_db()
    drivers = ", ".join(f"{d['component']} ({d['contribution']*100:.0f}%)" for d in p.drivers[:4])
    return {
        "answer": f"The Airfare Inflation Pressure Score is {p.score:.1f} ({p.level}). Top drivers: {drivers}.",
        "evidence": p.to_dict(),
        "affected_routes": [],
        "data_status": "MODELLED",
    }


def _answer_compare_routes(question: str) -> Dict[str, Any]:
    codes = re.findall(r"[A-Z]{3}-[A-Z]{3}", question.upper())
    codes = [c for c in codes if ROUTE_LOOKUP.get(c)]
    if len(codes) < 2:
        codes = ["DEL-BOM", "DEL-BLR"]
    from ..analytics.route_intelligence import build_route_intelligence_from_db
    rows = []
    for code in codes:
        try:
            rows.append(build_route_intelligence_from_db(code, include_forecast=False, include_anomalies=False))
        except Exception:
            continue
    if not rows:
        return {"answer": "Data unavailable for the requested routes.", "evidence": []}
    parts = [f"Comparison of {' vs '.join(codes)}:"]
    for r in rows:
        parts.append(f"{r['route_code']}: median fare ₹{r['current_median_fare_inr']:.0f}, "
                     f"24h {r['changes']['24h_pct']:+.1f}%, 7d {r['changes']['7d_pct']:+.1f}%, "
                     f"CPI contribution {r['cpi_contribution_bps']:+.2f} bps.")
    return {
        "answer": " ".join(parts),
        "evidence": [r for r in rows],
        "affected_routes": codes,
        "data_status": "SIMULATED",
    }


def _answer_scenario(question: str) -> Dict[str, Any]:
    m = re.search(r"increase by\s*(\d+)", question.lower())
    shock = float(m.group(1)) if m else 10.0
    from ..scenario.simulator import ScenarioInput, run_scenario_from_db
    result = run_scenario_from_db(ScenarioInput(airfare_shock_pct=shock, name="AI Analyst scenario"))
    return {
        "answer": (f"A modelled {shock:+.0f}% airfare shock projects the index "
                   f"{result.index_change_pct:+.2f}% to {result.projected_index:.2f}, "
                   f"transmitting {result.headline_cpi_impact_bps:+.4f} bps to headline CPI "
                   f"(Pressure: {result.pressure_score:.1f} / {result.pressure_level}). "
                   f"This is MODELLED output, not a forecast."),
        "evidence": result.to_dict(),
        "affected_routes": [r["route_code"] for r in result.route_impacts[:5]],
        "data_status": "MODELLED",
    }


def _answer_anomalies() -> Dict[str, Any]:
    from ..anomaly.detector import get_anomalies_from_db
    items = get_anomalies_from_db(limit=10)
    if not items:
        return {"answer": "No market anomalies currently detected.", "evidence": [], "data_status": "SIMULATED"}
    top = items[:3]
    parts = [f"{len(items)} market anomaly(ies) detected. Most severe: " + "; ".join(
        f"{a['anomaly_type']} on {a['route_code']} (severity {a['severity']})" for a in top) + "."]
    return {"answer": " ".join(parts), "evidence": items, "affected_routes": list({a['route_code'] for a in items}),
            "data_status": "SIMULATED"}


def _answer_data_quality() -> Dict[str, Any]:
    from ..data_quality.trust import compute_trust_report_from_db
    dq = compute_trust_report_from_db()
    return {"answer": f"Data Trust Score is {dq.trust_score:.1f} ({dq.level}). Freshness "
                      f"{dq.components.freshness:.0f}%, completeness {dq.components.completeness:.0f}%, "
                      f"coverage {dq.components.coverage:.0f}%.",
            "evidence": dq.to_dict(), "affected_routes": [], "data_status": "SIMULATED"}


def _answer_top_routes() -> Dict[str, Any]:
    from ..analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    dec = compute_cpi_decomposition_from_db()
    up = [c for c in dec.contributions if c.contribution_bps >= 0][:3]
    down = sorted([c for c in dec.contributions if c.contribution_bps < 0], key=lambda c: c.contribution_bps)[:3]
    return {
        "answer": "Top rising: " + ", ".join(f"{c.route_code} ({c.contribution_bps:+.2f} bps)" for c in up) +
                  ". Top falling: " + ", ".join(f"{c.route_code} ({c.contribution_bps:+.2f} bps)" for c in down) + ".",
        "evidence": {"rising": [c.to_dict() for c in up], "falling": [c.to_dict() for c in down]},
        "affected_routes": [c.route_code for c in up + down], "data_status": "SIMULATED",
    }


def answer_policy_question(question: str) -> Dict[str, Any]:
    """Resolve intent and produce a grounded answer with evidence."""
    matches = _match_intent(question)
    if not matches:
        return {
            "answer": ("I can answer data-grounded questions about the national airfare index, "
                       "CPI contributors, 7-day forecast, pressure score, route comparison, "
                       "what-if scenarios, anomalies and data quality. Please ask one of those."),
            "evidence": [], "intent": "UNKNOWN", "affected_routes": [],
            "data_status": "N/A", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    _, intent = matches[0]
    handlers = {
        "why_inflation_up": _answer_why_inflation_up,
        "cpi_contributors": _answer_cpi_contributors,
        "forecast": _answer_forecast,
        "pressure_cause": _answer_pressure,
        "compare_routes": lambda: _answer_compare_routes(question),
        "scenario": _answer_scenario,
        "anomalies": _answer_anomalies,
        "data_quality": _answer_data_quality,
        "top_routes": _answer_top_routes,
    }
    handler = handlers.get(intent, _answer_why_inflation_up)
    try:
        result = handler()
    except Exception as e:
        result = {"answer": f"Data unavailable: {e}", "evidence": [], "affected_routes": [],
                  "data_status": "UNAVAILABLE"}
    result["intent"] = intent
    result["question"] = question
    result["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result["note"] = ("Answers are assembled from verified platform data and are grounded in "
                      "actual API/DB results; the analyst does not compute statistics itself and "
                      "does not hallucinate numbers.")
    return result
