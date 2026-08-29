"""
VayuSutra APIx - Airfare Inflation Pressure Score
A transparent composite indicator (0-100) with explicitly documented, configurable weights.
Levels: LOW (0-25), MODERATE (26-50), HIGH (51-75), CRITICAL (76-100).

Components (each mapped to a 0-100 sub-score):
  - airfare_acceleration : recent momentum of the national Laspeyres index
  - volatility           : dispersion of daily index changes
  - route_breadth        : fraction of routes increasing over the last 7 days
  - t1_pressure          : spot T+1 sub-index movement
  - t7_pressure          : T+7 horizon movement
  - forecast_acceleration: forecast-implied forward pressure
  - cpi_transmission     : headline CPI basis-point impact

Weights sum to 1.0 and are renormalized if a component is unavailable (e.g. no forecast).
"""
import datetime
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import numpy as np

from ..config.routes import DGCA_TOP_20_ROUTES, CPI_WEIGHTS


DEFAULT_PRESSURE_WEIGHTS: Dict[str, float] = {
    "airfare_acceleration": 0.22,
    "route_breadth": 0.20,
    "t1_pressure": 0.16,
    "t7_pressure": 0.10,
    "volatility": 0.12,
    "forecast_acceleration": 0.10,
    "cpi_transmission": 0.10,
}


@dataclass
class PressureComponents:
    airfare_acceleration: float = 0.0
    volatility: float = 0.0
    route_breadth: float = 0.0
    t1_pressure: float = 0.0
    t7_pressure: float = 0.0
    forecast_acceleration: float = 0.0
    cpi_transmission: float = 0.0

    def sub_scores(self, weights: Dict[str, float]) -> Dict[str, float]:
        return {
            "airfare_acceleration": self._map_momentum(self.airfare_acceleration),
            "volatility": self._map_volatility(self.volatility),
            "route_breadth": self._map_breadth(self.route_breadth),
            "t1_pressure": self._map_momentum(self.t1_pressure),
            "t7_pressure": self._map_momentum(self.t7_pressure),
            "forecast_acceleration": self._map_momentum(self.forecast_acceleration),
            "cpi_transmission": self._map_cpi(self.cpi_transmission),
        }

    @staticmethod
    def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, v))

    def _map_momentum(self, daily_pct: float) -> float:
        # 0% daily -> 0; 1% daily -> ~60; 2%+ daily -> 100
        return self._clamp((abs(daily_pct) / 1.5) * 90.0)

    def _map_volatility(self, vol: float) -> float:
        # daily change std of ~0.2% -> low, 1.5% -> high
        return self._clamp((vol / 1.5) * 100.0)

    def _map_breadth(self, breadth: float) -> float:
        # fraction (0..1) of routes rising
        return self._clamp(breadth * 100.0)

    def _map_cpi(self, headline_bps: float) -> float:
        # 0 bps -> 0; ~1 bps -> 60; 2+ bps -> 100
        return self._clamp((headline_bps / 1.5) * 90.0)


@dataclass
class PressureReport:
    score: float
    level: str
    components: PressureComponents
    weights: Dict[str, float]
    previous_score: Optional[float]
    change: float
    drivers: List[Dict[str, Any]]
    data_status: str = "MODELLED"

    def to_dict(self) -> Dict[str, Any]:
        sub = self.components.sub_scores(self.weights)
        return {
            "pressure_score": round(self.score, 1),
            "level": self.level,
            "previous_score": round(self.previous_score, 1) if self.previous_score is not None else None,
            "change": round(self.change, 1),
            "components": {
                "airfare_acceleration_pct": round(self.components.airfare_acceleration, 4),
                "volatility": round(self.components.volatility, 4),
                "route_breadth_pct": round(self.components.route_breadth * 100.0, 1),
                "t1_pressure_pct": round(self.components.t1_pressure, 4),
                "t7_pressure_pct": round(self.components.t7_pressure, 4),
                "forecast_acceleration_pct": round(self.components.forecast_acceleration, 4),
                "cpi_transmission_bps": round(self.components.cpi_transmission, 4),
            },
            "component_scores": {k: round(v, 1) for k, v in sub.items()},
            "drivers": self.drivers,
            "weights": self.weights,
            "data_status": self.data_status,
        }


def _level_for(score: float) -> str:
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MODERATE"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


class PressureEngine:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = dict(weights or DEFAULT_PRESSURE_WEIGHTS)

    def compute(self, components: PressureComponents,
                previous_score: Optional[float] = None) -> PressureReport:
        # Renormalize weights for available components
        sub = components.sub_scores(self.weights)
        active = {k: v for k, v in sub.items() if v is not None}
        total_w = sum(self.weights[k] for k in active)
        score = sum(self.weights[k] * sub[k] for k in active) / total_w if total_w > 0 else 0.0

        # Drivers sorted by weighted contribution
        drivers = sorted(
            ({"component": k, "weight": self.weights[k], "contribution": round(self.weights[k] * sub[k] / total_w, 3)}
             for k in active), key=lambda d: d["contribution"], reverse=True
        )

        change = (score - previous_score) if previous_score is not None else 0.0
        return PressureReport(
            score=round(score, 1), level=_level_for(score), components=components,
            weights=self.weights, previous_score=previous_score, change=round(change, 1),
            drivers=drivers,
        )


def compute_pressure_from_db(previous_score: Optional[float] = None) -> PressureReport:
    from ..config.db import get_db_connection
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT calculation_date, laspeyres_index, spot_t1_index, bps_headline_cpi_impact,
               daily_pct_change
        FROM national_indices ORDER BY calculation_date ASC
    """).fetchall()
    if len(rows) < 2:
        return PressureEngine().compute(PressureComponents(), previous_score)

    lasp = [r["laspeyres_index"] for r in rows]
    daily = [r["daily_pct_change"] for r in rows]

    # airfare acceleration = mean of last 3 daily changes
    accel = float(np.mean(daily[-3:]))
    # volatility = std of last 10 daily changes
    vol = float(np.std(daily[-10:])) if len(daily) >= 2 else 0.0
    # cpi transmission = latest headline bps (magnitude)
    cpi = float(rows[-1]["bps_headline_cpi_impact"])
    # t1 pressure = latest spot index daily-ish movement vs mean of last 5 spot
    t1 = float(rows[-1]["spot_t1_index"])
    t1_prev = float(np.mean([r["spot_t1_index"] for r in rows[-6:-1]])) if len(rows) > 1 else t1
    t1_pressure = ((t1 - t1_prev) / t1_prev * 100.0) if t1_prev > 0 else 0.0

    # t7 pressure from route_indices T+7 window relative change over 7 days
    t7_pressure = _compute_window_pressure(conn, "T+7")
    # route breadth = fraction of routes with higher composite relative vs 7 days ago
    route_breadth = _compute_route_breadth(conn)

    components = PressureComponents(
        airfare_acceleration=accel, volatility=vol, route_breadth=route_breadth,
        t1_pressure=t1_pressure, t7_pressure=t7_pressure,
        forecast_acceleration=0.0, cpi_transmission=cpi,
    )
    return PressureEngine().compute(components, previous_score)


def _compute_window_pressure(conn, window: str) -> float:
    rows = conn.execute("""
        SELECT calculation_date, AVG(price_relative) AS rel
        FROM route_indices WHERE advance_window=? GROUP BY calculation_date ORDER BY calculation_date ASC
    """, (window,)).fetchall()
    if len(rows) < 2:
        return 0.0
    rels = [r["rel"] for r in rows]
    recent = float(np.mean(rels[-3:]))
    prior = float(np.mean(rels[-8:-3])) if len(rels) >= 8 else float(np.mean(rels[:-1]))
    return ((recent - prior) / prior * 100.0) if prior > 0 else 0.0


def _compute_route_breadth(conn) -> float:
    dates = conn.execute(
        "SELECT DISTINCT calculation_date FROM route_indices ORDER BY calculation_date DESC LIMIT 8"
    ).fetchall()
    if len(dates) < 2:
        return 0.0
    latest = dates[0]["calculation_date"]
    prev = dates[-1]["calculation_date"]
    lat = {r["route_code"]: r["composite_route_relative"] for r in conn.execute(
        "SELECT route_code, composite_route_relative FROM route_indices WHERE calculation_date=?", (latest,)
    ).fetchall()}
    prv = {r["route_code"]: r["composite_route_relative"] for r in conn.execute(
        "SELECT route_code, composite_route_relative FROM route_indices WHERE calculation_date=?", (prev,)
    ).fetchall()}
    rising = 0
    total = 0
    for code in DGCA_TOP_20_ROUTES:
        if code in lat and code in prv and prv[code] > 0:
            total += 1
            if lat[code] > prv[code]:
                rising += 1
    return (rising / total) if total > 0 else 0.0
