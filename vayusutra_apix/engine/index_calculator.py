"""
VayuSutra APIx - Statutory Econometric Index Calculation Engine (Superlative & Regional Class)
Implements Jevons Geometric Mean, Laspeyres Fixed-Weight Basket, Paasche Index with Elasticity,
Fisher Ideal Index, Törnqvist Superlative Index, Walsh Geometric Weight Index,
Chained Index Formulation, and Regional Macro Inflation Disaggregation.
"""

import datetime
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

from ..config.routes import (
    DGCA_TOP_20_ROUTES,
    ADVANCE_PURCHASE_WINDOWS,
    BASE_PERIOD_BENCHMARKS,
    CPI_WEIGHTS,
    ROUTE_LOOKUP,
    WINDOW_LOOKUP,
)
from ..pipeline.validator import CleanedFlightQuote

logger = logging.getLogger("vayusutra.engine")


@dataclass
class RouteElementaryResult:
    """Elementary index calculation result for a single route-window cell."""
    calculation_date: str
    route_code: str
    advance_window: str
    sample_size: int
    jevons_mean_fare: float
    base_benchmark_fare: float
    price_relative: float


@dataclass
class RegionalIndexBreakdown:
    """Regional and state corridor inflation sub-indices."""
    delhi_ncr_index: float
    mumbai_mmr_index: float
    bengaluru_karnataka_index: float
    eastern_hub_index: float
    southern_hub_index: float


@dataclass
class SuperlativeIndexMetrics:
    """Comparison across standard and UN/ILO Superlative index formulas."""
    laspeyres_index: float
    paasche_index: float
    fisher_ideal_index: float
    tornqvist_index: float
    walsh_index: float
    jevons_national_index: float
    substitution_bias_laspeyres_vs_fisher: float
    substitution_bias_laspeyres_vs_tornqvist: float


@dataclass
class NationalIndexCalculation:
    """Master National Airfare Price Index and CPI Transmission Output."""
    calculation_date: str
    laspeyres_index: float
    paasche_index: float
    fisher_index: float
    tornqvist_index: float
    walsh_index: float
    jevons_index: float
    spot_t1_index: float
    chained_index: float
    daily_pct_change: float
    bps_transport_impact: float
    bps_headline_cpi_impact: float
    substitution_bias_bps: float
    regional_breakdown: RegionalIndexBreakdown
    route_relatives: Dict[str, float]
    window_relatives: Dict[str, float]
    elementary_results: List[RouteElementaryResult]
    total_quotes_evaluated: int
    valid_quotes_count: int
    outliers_rejected_count: int


class IndexCalculationEngine:
    """
    Core quantitative econometric engine executing MoSPI, RBI, and ILO Diewert Superlative price index math.
    """

    def __init__(self):
        self.routes = DGCA_TOP_20_ROUTES
        self.windows = ADVANCE_PURCHASE_WINDOWS
        self.base_benchmarks = BASE_PERIOD_BENCHMARKS
        self.cpi_weights = CPI_WEIGHTS
        self.elasticity = CPI_WEIGHTS["demand_price_elasticity"]  # -0.85

    @staticmethod
    def calculate_jevons_geometric_mean(fares: List[float]) -> float:
        """
        Computes Jevons Geometric Mean:
        P_bar = (prod p_i)^(1/n) = exp(1/n * sum ln(p_i))
        """
        if not fares:
            return 0.0
        arr = np.array(fares, dtype=float)
        arr = np.clip(arr, a_min=1.0, a_max=None)
        return float(np.exp(np.mean(np.log(arr))))

    def compute_elementary_aggregates(
        self,
        cleaned_quotes: List[CleanedFlightQuote],
        calculation_date: str
    ) -> Tuple[List[RouteElementaryResult], Dict[str, Dict[str, float]]]:
        """
        Computes elementary price relatives R_{r,k}^t for each route and advance purchase window.
        """
        strata_fares: Dict[Tuple[str, str], List[float]] = {}
        for r in self.routes:
            for w in self.windows:
                strata_fares[(r.route_code, w.window_id)] = []

        for q in cleaned_quotes:
            if q.outlier_flag == 0 and q.deduplication_kept == 1:
                key = (q.route_code, q.advance_window)
                if key in strata_fares:
                    strata_fares[key].append(q.final_total_fare)

        elementary_results: List[RouteElementaryResult] = []
        relatives_map: Dict[str, Dict[str, float]] = {r.route_code: {} for r in self.routes}

        for r in self.routes:
            for w in self.windows:
                fares = strata_fares.get((r.route_code, w.window_id), [])
                p0 = self.base_benchmarks.get(r.route_code, {}).get(w.window_id, r.base_fare_benchmark)

                if fares:
                    jevons_mean = self.calculate_jevons_geometric_mean(fares)
                else:
                    jevons_mean = p0

                price_rel = jevons_mean / p0 if p0 > 0 else 1.0
                relatives_map[r.route_code][w.window_id] = price_rel

                elementary_results.append(RouteElementaryResult(
                    calculation_date=calculation_date,
                    route_code=r.route_code,
                    advance_window=w.window_id,
                    sample_size=len(fares),
                    jevons_mean_fare=round(jevons_mean, 2),
                    base_benchmark_fare=round(p0, 2),
                    price_relative=round(price_rel, 6),
                ))

        return elementary_results, relatives_map

    def compute_national_indices(
        self,
        elementary_results: List[RouteElementaryResult],
        relatives_map: Dict[str, Dict[str, float]],
        calculation_date: str,
        previous_laspeyres_index: Optional[float] = None,
        previous_chained_index: Optional[float] = None,
        total_quotes: int = 0,
        valid_quotes: int = 0,
        outliers_count: int = 0
    ) -> NationalIndexCalculation:
        """
        Computes composite route relatives, Superlative Indices (Fisher, Törnqvist, Walsh),
        Regional sub-indices, Chained relatives, and CPI transmission bps.
        """
        # 1. Route Composite Relatives: R_bar_r = sum_k alpha_k * R_{r,k}
        composite_route_relatives: Dict[str, float] = {}
        for r in self.routes:
            r_comp = 0.0
            for w in self.windows:
                alpha = w.weight
                r_k = relatives_map.get(r.route_code, {}).get(w.window_id, 1.0)
                r_comp += alpha * r_k
            composite_route_relatives[r.route_code] = r_comp

        # 2. Advance Purchase Window Aggregates across all routes
        window_relatives: Dict[str, float] = {}
        for w in self.windows:
            w_rel = sum(r.weight * relatives_map.get(r.route_code, {}).get(w.window_id, 1.0) for r in self.routes)
            window_relatives[w.window_id] = round(w_rel * 100.0, 2)

        # 3. Laspeyres Index: I_L = (sum w_r^0 * R_bar_r) * 100
        laspeyres_val = sum(r.weight * composite_route_relatives[r.route_code] for r in self.routes) * 100.0

        # 4. Paasche Index with Demand Substitution:
        eps = self.elasticity  # -0.85
        paasche_num = sum(r.weight * (composite_route_relatives[r.route_code] ** (1.0 + eps)) for r in self.routes)
        paasche_den = sum(r.weight * (composite_route_relatives[r.route_code] ** eps) for r in self.routes)
        paasche_val = (paasche_num / paasche_den) * 100.0 if paasche_den > 0 else laspeyres_val

        # Current period expenditure weights w_r^t
        current_weights = {}
        total_curr_denom = sum(r.weight * (composite_route_relatives[r.route_code] ** (1.0 + eps)) for r in self.routes)
        for r in self.routes:
            current_weights[r.route_code] = (r.weight * (composite_route_relatives[r.route_code] ** (1.0 + eps))) / total_curr_denom if total_curr_denom > 0 else r.weight

        # 5. Fisher Ideal Index: I_F = sqrt(I_L * I_P)
        fisher_val = math.sqrt(laspeyres_val * paasche_val)

        # 6. Törnqvist Superlative Index: ln(I_T/100) = sum (w_r^0 + w_r^t)/2 * ln(R_bar_r)
        tornqvist_log = sum(
            ((r.weight + current_weights[r.route_code]) / 2.0) * math.log(max(1e-6, composite_route_relatives[r.route_code]))
            for r in self.routes
        )
        tornqvist_val = math.exp(tornqvist_log) * 100.0

        # 7. Walsh Geometric Weight Superlative Index: I_W = sum sqrt(w_r^0 * w_r^t) * R_bar_r / sum sqrt(w_r^0 * w_r^t) * 100
        walsh_num = sum(math.sqrt(r.weight * current_weights[r.route_code]) * composite_route_relatives[r.route_code] for r in self.routes)
        walsh_den = sum(math.sqrt(r.weight * current_weights[r.route_code]) for r in self.routes)
        walsh_val = (walsh_num / walsh_den) * 100.0 if walsh_den > 0 else laspeyres_val

        # 8. Jevons National Index
        log_sum = sum(r.weight * math.log(max(1e-6, composite_route_relatives[r.route_code])) for r in self.routes)
        jevons_val = math.exp(log_sum) * 100.0

        # 9. Spot T+1 National Sub-Index
        spot_t1_val = sum(r.weight * relatives_map.get(r.route_code, {}).get("T+1", 1.0) for r in self.routes) * 100.0

        # 10. Chained Index Calculation
        if previous_chained_index is not None and previous_laspeyres_index is not None and previous_laspeyres_index > 0:
            chained_val = previous_chained_index * (laspeyres_val / previous_laspeyres_index)
        else:
            chained_val = laspeyres_val

        # 11. Daily Change and CPI Transmission
        if previous_laspeyres_index is not None and previous_laspeyres_index > 0:
            daily_pct = ((laspeyres_val - previous_laspeyres_index) / previous_laspeyres_index) * 100.0
        else:
            daily_pct = 0.0

        w_airfare = self.cpi_weights["airfare_share_within_transport"]  # 0.0385
        w_transport = self.cpi_weights["transport_and_communication_cpi_weight"]  # 0.0859

        bps_transport = daily_pct * w_airfare * 100.0
        bps_headline = bps_transport * w_transport
        sub_bias_bps = (laspeyres_val - fisher_val) * w_airfare * 100.0

        # 12. Regional State / Metro Corridor Disaggregation
        delhi_routes = [r for r in self.routes if "DEL" in r.route_code]
        mumbai_routes = [r for r in self.routes if "BOM" in r.route_code]
        blr_routes = [r for r in self.routes if "BLR" in r.route_code]
        east_routes = [r for r in self.routes if "CCU" in r.route_code]
        south_routes = [r for r in self.routes if "HYD" in r.route_code or "MAA" in r.route_code]

        def compute_sub_region(routes_subset):
            tot_w = sum(r.weight for r in routes_subset)
            if tot_w <= 0: return 100.0
            return (sum(r.weight * composite_route_relatives[r.route_code] for r in routes_subset) / tot_w) * 100.0

        regional_breakdown = RegionalIndexBreakdown(
            delhi_ncr_index=round(compute_sub_region(delhi_routes), 2),
            mumbai_mmr_index=round(compute_sub_region(mumbai_routes), 2),
            bengaluru_karnataka_index=round(compute_sub_region(blr_routes), 2),
            eastern_hub_index=round(compute_sub_region(east_routes), 2),
            southern_hub_index=round(compute_sub_region(south_routes), 2),
        )

        return NationalIndexCalculation(
            calculation_date=calculation_date,
            laspeyres_index=round(laspeyres_val, 2),
            paasche_index=round(paasche_val, 2),
            fisher_index=round(fisher_val, 2),
            tornqvist_index=round(tornqvist_val, 2),
            walsh_index=round(walsh_val, 2),
            jevons_index=round(jevons_val, 2),
            spot_t1_index=round(spot_t1_val, 2),
            chained_index=round(chained_val, 2),
            daily_pct_change=round(daily_pct, 4),
            bps_transport_impact=round(bps_transport, 4),
            bps_headline_cpi_impact=round(bps_headline, 4),
            substitution_bias_bps=round(sub_bias_bps, 4),
            regional_breakdown=regional_breakdown,
            route_relatives={k: round(v, 4) for k, v in composite_route_relatives.items()},
            window_relatives=window_relatives,
            elementary_results=elementary_results,
            total_quotes_evaluated=total_quotes,
            valid_quotes_count=valid_quotes,
            outliers_rejected_count=outliers_count,
        )
