"""
VayuSutra APIx - CPI Impact Decomposition (route-level)
Decomposes the headline CPI basis-point impact into per-route contributions so a policy
analyst can answer "why did CPI move?". Every contribution is derived from actual
composite route relatives in the `route_indices` table.
"""
import datetime
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

from ..config.routes import DGCA_TOP_20_ROUTES, CPI_WEIGHTS, ROUTE_LOOKUP


@dataclass
class RouteCPIContribution:
    route_code: str
    weight: float
    price_movement_pct: float
    contribution_bps: float
    cumulative_bps: float
    direction: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_code": self.route_code,
            "route_name": f"{self.route_code}",
            "weight": round(self.weight, 4),
            "price_movement_pct": round(self.price_movement_pct, 4),
            "contribution_bps": round(self.contribution_bps, 4),
            "cumulative_bps": round(self.cumulative_bps, 4),
            "direction": self.direction,
        }


@dataclass
class CPIDecompositionReport:
    headline_impact_bps: float
    transport_impact_bps: float
    as_of_date: str
    contributions: List[RouteCPIContribution]
    method: str = "Route composite-relative share of Laspeyres daily change"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "headline_cpi_impact_bps": round(self.headline_impact_bps, 4),
            "transport_subgroup_impact_bps": round(self.transport_impact_bps, 4),
            "as_of_date": self.as_of_date,
            "method": self.method,
            "total_contributions_sum_bps": round(sum(c.contribution_bps for c in self.contributions), 4),
            "contributors": [c.to_dict() for c in self.contributions],
        }


class CPIDecompositionEngine:
    def __init__(self):
        self.w_air = CPI_WEIGHTS["airfare_share_within_transport"]
        self.w_trans = CPI_WEIGHTS["transport_and_communication_cpi_weight"]

    def decompose(self, prev_relatives: Dict[str, float],
                  curr_relatives: Dict[str, float]) -> CPIDecompositionReport:
        # index_base_{t-1} in relative units (index/100)
        index_base_prev = sum(r.weight * prev_relatives.get(r.route_code, 1.0) for r in DGCA_TOP_20_ROUTES)
        index_base_prev = max(index_base_prev, 1e-6)

        contributions: List[RouteCPIContribution] = []
        cum = 0.0
        for r in DGCA_TOP_20_ROUTES:
            r_prev = prev_relatives.get(r.route_code, 1.0)
            r_curr = curr_relatives.get(r.route_code, 1.0)
            # Route share of the daily percentage change (percentage points)
            route_daily_pct = (r.weight * (r_curr - r_prev)) / index_base_prev * 100.0
            # Convert route daily pct into headline CPI bps
            contribution_bps = route_daily_pct * self.w_air * 100.0 * self.w_trans
            cum += contribution_bps
            movement_pct = ((r_curr - r_prev) / r_prev * 100.0) if r_prev > 0 else 0.0
            contributions.append(RouteCPIContribution(
                route_code=r.route_code,
                weight=r.weight,
                price_movement_pct=movement_pct,
                contribution_bps=contribution_bps,
                cumulative_bps=cum,
                direction="UP" if contribution_bps > 0 else "DOWN" if contribution_bps < 0 else "FLAT",
            ))

        headline_bps = sum(c.contribution_bps for c in contributions)
        transport_bps = headline_bps / self.w_trans if self.w_trans > 0 else 0.0

        # Order by absolute contribution (largest first)
        contributions.sort(key=lambda c: abs(c.contribution_bps), reverse=True)
        # recompute cumulative after sorting
        cum = 0.0
        for c in contributions:
            cum += c.contribution_bps
            c.cumulative_bps = cum

        return CPIDecompositionReport(
            headline_impact_bps=headline_bps,
            transport_impact_bps=transport_bps,
            as_of_date=datetime.date.today().isoformat(),
            contributions=contributions,
        )


def compute_cpi_decomposition_from_db() -> CPIDecompositionReport:
    from ..config.db import get_db_connection
    conn = get_db_connection()
    dates = conn.execute(
        "SELECT DISTINCT calculation_date FROM route_indices ORDER BY calculation_date DESC LIMIT 2"
    ).fetchall()
    if len(dates) < 2:
        # Only one day available; use base relatives (1.0) as previous
        prev = {r.route_code: 1.0 for r in DGCA_TOP_20_ROUTES}
        if dates:
            curr = _load_relatives(conn, dates[0]["calculation_date"])
        else:
            curr = prev
    else:
        curr_dt, prev_dt = dates[0]["calculation_date"], dates[1]["calculation_date"]
        curr = _load_relatives(conn, curr_dt)
        prev = _load_relatives(conn, prev_dt)
    return CPIDecompositionEngine().decompose(prev, curr)


def _load_relatives(conn, calc_date: str) -> Dict[str, float]:
    rows = conn.execute(
        "SELECT route_code, composite_route_relative FROM route_indices WHERE calculation_date=?",
        (calc_date,)
    ).fetchall()
    return {r["route_code"]: r["composite_route_relative"] for r in rows}
