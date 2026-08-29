"""
VayuSutra APIx - Data Cleaning, Outlier Rejection & Deduplication Pipeline
Implements Multi-OTA Deduplication, Median Absolute Deviation (MAD) Modified Z-Score,
Tukey's IQR filter, and statutory tax decomposition.
"""

import datetime
import logging
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

from .validator import RawFlightQuote, CleanedFlightQuote

logger = logging.getLogger("vayusutra.cleaner")


@dataclass
class CleaningSummary:
    """Telemetry report produced after data ingestion and cleaning."""
    total_raw_quotes: int
    deduplicated_quotes_retained: int
    duplicates_dropped: int
    outliers_flagged: int
    valid_quotes_retained: int
    routes_covered: int
    execution_time_ms: float


class DataCleaningPipeline:
    """
    Robust econometric data scrubbing pipeline ensuring zero bias from duplicate OTA quotes
    and filtering aberrant price spikes/crawling artifacts before index computation.
    """

    def __init__(self, mad_threshold: float = 3.0, iqr_multiplier: float = 1.5):
        self.mad_threshold = mad_threshold
        self.iqr_multiplier = iqr_multiplier

    def deduplicate_multi_ota(self, quotes: List[RawFlightQuote]) -> Tuple[List[RawFlightQuote], List[RawFlightQuote]]:
        """
        Deduplicates quotes where identical physical flights appear across both direct airline
        and multiple OTA portals (MakeMyTrip, EaseMyTrip, Cleartrip). Direct airline quote is preferred.
        """
        flight_groups: Dict[Tuple[str, str, str], List[RawFlightQuote]] = defaultdict(list)

        for q in quotes:
            # Group key: (flight_number, travel_date, departure_time)
            key = (q.flight_number.strip().upper(), q.travel_date, q.departure_time.strip())
            flight_groups[key].append(q)

        retained: List[RawFlightQuote] = []
        dropped_duplicates: List[RawFlightQuote] = []

        for key, group in flight_groups.items():
            if len(group) == 1:
                retained.append(group[0])
                continue

            # Prioritize direct airline portal quote
            direct_quotes = [q for q in group if q.is_direct == 1]
            if direct_quotes:
                best_quote = direct_quotes[0]
                retained.append(best_quote)
                for q in group:
                    if q.quote_id != best_quote.quote_id:
                        dropped_duplicates.append(q)
            else:
                # If no direct quote, pick the one with lowest net fare (total - convenience_fee)
                best_quote = min(group, key=lambda x: (x.total_fare - x.convenience_fee))
                retained.append(best_quote)
                for q in group:
                    if q.quote_id != best_quote.quote_id:
                        dropped_duplicates.append(q)

        return retained, dropped_duplicates

    def detect_outliers_mad(self, fares: np.ndarray) -> np.ndarray:
        """
        Computes Modified Z-scores using Median Absolute Deviation (MAD):
            MAD = median(|x_i - median(x)|)
            M_i = 0.6745 * (x_i - median(x)) / MAD
        Returns boolean mask where True indicates an outlier.
        """
        if len(fares) == 0:
            return np.zeros(0, dtype=bool)

        if len(fares) < 3:
            if len(fares) == 2:
                min_f = np.min(fares)
                max_f = np.max(fares)
                if min_f > 0 and (max_f / min_f) >= 3.0:
                    return fares == max_f
                return (fares > 75000.0) | (fares < 500.0)
            elif len(fares) == 1:
                return (fares > 75000.0) | (fares < 500.0)

        med = np.median(fares)
        abs_deviation = np.abs(fares - med)
        mad = np.median(abs_deviation)

        if mad > 1e-4:
            modified_z = 0.6745 * abs_deviation / mad
            return (modified_z > self.mad_threshold) | (fares > 75000.0) | (fares < 500.0)
        else:
            # Fallback to Tukey's IQR if MAD is zero (e.g. tight cluster with few spikes)
            q25, q75 = np.percentile(fares, [25, 75])
            iqr = q75 - q25
            if iqr > 1e-4:
                lower = q25 - (self.iqr_multiplier * iqr)
                upper = q75 + (self.iqr_multiplier * iqr)
                return (fares < lower) | (fares > upper) | (fares > 75000.0) | (fares < 500.0)
            else:
                # Extreme heuristic fallback
                return (fares < 0.3 * med) | (fares > 3.0 * med) | (fares > 75000.0) | (fares < 500.0)

    def process_and_clean(
        self,
        raw_quotes_data: List[Dict[str, Any]]
    ) -> Tuple[List[CleanedFlightQuote], CleaningSummary]:
        """
        Executes full pipeline:
        1. Parse & validate RawFlightQuote schemas.
        2. Multi-OTA deduplication.
        3. Stratified MAD outlier rejection by (route_code, advance_window, booking_date).
        4. Statutory tax decomposition and finalization.
        """
        start_time = datetime.datetime.now()
        
        # 1. Validation
        valid_raw: List[RawFlightQuote] = []
        for item in raw_quotes_data:
            try:
                valid_raw.append(RawFlightQuote(**item))
            except Exception as e:
                logger.warning(f"Discarding invalid quote: {e}")

        total_raw = len(valid_raw)

        # 2. Multi-OTA Deduplication
        dedup_retained, dedup_dropped = self.deduplicate_multi_ota(valid_raw)
        duplicates_dropped_count = len(dedup_dropped)

        # 3. Stratified Outlier Detection
        strata: Dict[Tuple[str, str, str], List[RawFlightQuote]] = defaultdict(list)
        for q in dedup_retained:
            strata[(q.route_code, q.advance_window, q.booking_date)].append(q)

        cleaned_results: List[CleanedFlightQuote] = []
        outliers_count = 0
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        routes_seen = set()

        for (route_code, adv_win, b_date), quotes_group in strata.items():
            routes_seen.add(route_code)
            fares = np.array([q.total_fare for q in quotes_group], dtype=float)
            outlier_mask = self.detect_outliers_mad(fares)

            for idx, q in enumerate(quotes_group):
                is_outlier = bool(outlier_mask[idx])
                reason = None

                if is_outlier:
                    outliers_count += 1
                    reason = f"MAD Modified Z-score > {self.mad_threshold} on fare Rs. {q.total_fare:.2f}"
                elif q.total_fare < 500.0:
                    is_outlier = True
                    outliers_count += 1
                    reason = f"Sub-statutory price floor violation: Rs. {q.total_fare:.2f}"
                elif q.total_fare > 150000.0:
                    is_outlier = True
                    outliers_count += 1
                    reason = f"Super-ceiling price anomaly: Rs. {q.total_fare:.2f}"

                # Statutory clean tax and base decomposition
                tax_fee_component = round(q.fuel_surcharge + q.udf + q.psf + q.asf + q.gst, 2)
                
                cleaned_obj = CleanedFlightQuote(
                    cleaned_id=f"CLN-{uuid.uuid4().hex[:12]}",
                    raw_quote_id=q.quote_id,
                    route_code=q.route_code,
                    advance_window=q.advance_window,
                    booking_date=q.booking_date,
                    travel_date=q.travel_date,
                    airline_code=q.airline_code,
                    flight_number=q.flight_number,
                    final_base_fare=round(q.base_fare, 2),
                    final_tax_fee=tax_fee_component,
                    final_total_fare=round(q.total_fare - (q.convenience_fee if q.is_direct == 0 else 0.0), 2),
                    outlier_flag=1 if is_outlier else 0,
                    outlier_reason=reason,
                    deduplication_kept=1,
                    cleaned_at=now_iso,
                )
                cleaned_results.append(cleaned_obj)

        end_time = datetime.datetime.now()
        exec_ms = (end_time - start_time).total_seconds() * 1000.0
        valid_retained = len([c for c in cleaned_results if c.outlier_flag == 0])

        summary = CleaningSummary(
            total_raw_quotes=total_raw,
            deduplicated_quotes_retained=len(dedup_retained),
            duplicates_dropped=duplicates_dropped_count,
            outliers_flagged=outliers_count,
            valid_quotes_retained=valid_retained,
            routes_covered=len(routes_seen),
            execution_time_ms=round(exec_ms, 2)
        )

        return cleaned_results, summary
