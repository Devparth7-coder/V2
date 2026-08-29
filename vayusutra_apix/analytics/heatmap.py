"""
VayuSutra APIx - Airfare Heatmap (20 routes x 5 booking horizons)
Each cell reports current Jevons mean fare, price change (24h), volatility and a status
colour. Built deterministically from the `route_indices` table.
"""
import datetime
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import numpy as np

from ..config.routes import DGCA_TOP_20_ROUTES, ADVANCE_PURCHASE_WINDOWS, ROUTE_LOOKUP


@dataclass
class HeatmapCell:
    route_code: str
    advance_window: str
    current_fare: float
    price_change_pct: float
    volatility: float
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_code": self.route_code,
            "advance_window": self.advance_window,
            "current_fare": round(self.current_fare, 2),
            "price_change_pct": round(self.price_change_pct, 2),
            "volatility": round(self.volatility, 4),
            "status": self.status,
        }


@dataclass
class RouteHeatmap:
    as_of_date: str
    routes: List[str]
    windows: List[str]
    cells: List[HeatmapCell]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "routes": self.routes,
            "windows": self.windows,
            "cells": [c.to_dict() for c in self.cells],
        }


def _status_for(change: float) -> str:
    if change >= 5.0:
        return "SURGE"
    if change >= 2.0:
        return "RISING"
    if change <= -5.0:
        return "DROP"
    if change <= -2.0:
        return "FALLING"
    return "STABLE"


class HeatmapEngine:
    def build(self, latest: Dict[str, Dict[str, dict]],
              previous: Dict[str, Dict[str, dict]],
              volatility: Dict[tuple, float]) -> RouteHeatmap:
        cells: List[HeatmapCell] = []
        as_of = datetime.date.today().isoformat()
        for r in DGCA_TOP_20_ROUTES:
            for w in ADVANCE_PURCHASE_WINDOWS:
                cur = latest.get(r.route_code, {}).get(w.window_id)
                prev = previous.get(r.route_code, {}).get(w.window_id)
                cur_fare = cur["jevons_mean_fare"] if cur else (prev["jevons_mean_fare"] if prev else 0.0)
                prev_fare = prev["jevons_mean_fare"] if prev else cur_fare
                change = ((cur_fare - prev_fare) / prev_fare * 100.0) if prev_fare and prev_fare > 0 else 0.0
                vol = volatility.get((r.route_code, w.window_id), 0.0)
                cells.append(HeatmapCell(
                    route_code=r.route_code,
                    advance_window=w.window_id,
                    current_fare=cur_fare,
                    price_change_pct=change,
                    volatility=vol,
                    status=_status_for(change),
                ))
        return RouteHeatmap(as_of_date=as_of, routes=[r.route_code for r in DGCA_TOP_20_ROUTES],
                            windows=[w.window_id for w in ADVANCE_PURCHASE_WINDOWS], cells=cells)


def build_heatmap_from_db(volatility_window: int = 7) -> RouteHeatmap:
    from ..config.db import get_db_connection
    conn = get_db_connection()
    dates = conn.execute(
        "SELECT DISTINCT calculation_date FROM route_indices ORDER BY calculation_date DESC LIMIT 2"
    ).fetchall()
    latest_map: Dict[str, Dict[str, dict]] = {}
    prev_map: Dict[str, Dict[str, dict]] = {}
    if dates:
        _fill(conn, dates[0]["calculation_date"], latest_map)
        if len(dates) >= 2:
            _fill(conn, dates[1]["calculation_date"], prev_map)

    # Volatility from recent history of jevons_mean_fare per route-window
    history_rows = conn.execute("""
        SELECT route_code, advance_window, jevons_mean_fare
        FROM route_indices
        WHERE jevons_mean_fare > 0
        ORDER BY calculation_date DESC
    """).fetchall()
    vol_map: Dict[tuple, float] = {}
    hist: Dict[tuple, List[float]] = {}
    for row in history_rows:
        hist.setdefault((row["route_code"], row["advance_window"]), []).append(row["jevons_mean_fare"])
    for key, fares in hist.items():
        arr = np.array(fares[:volatility_window], dtype=float)
        if len(arr) > 1:
            med = float(np.mean(arr))
            vol_map[key] = float(np.std(arr) / med) if med > 0 else 0.0
        else:
            vol_map[key] = 0.0

    return HeatmapEngine().build(latest_map, prev_map, vol_map)


def _fill(conn, calc_date: str, target: Dict[str, Dict[str, dict]]) -> None:
    rows = conn.execute("""
        SELECT route_code, advance_window, jevons_mean_fare, price_relative
        FROM route_indices WHERE calculation_date=?
    """, (calc_date,)).fetchall()
    for row in rows:
        target.setdefault(row["route_code"], {})[row["advance_window"]] = {
            "jevons_mean_fare": row["jevons_mean_fare"],
            "price_relative": row["price_relative"],
        }
