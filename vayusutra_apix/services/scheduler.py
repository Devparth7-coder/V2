"""
VayuSutra APIx - Autonomous Ingestion & Model Retraining Background Worker Daemon
Runs continuous high-frequency scheduled tasks, emits WebSocket events, and updates Prometheus metrics.
"""

import asyncio
import datetime
import logging
import time
from typing import Dict, Any, Optional

from .streaming import stream_manager
from .metrics import (
    QUOTES_INGESTED_TOTAL,
    QUOTES_REJECTED_OUTLIERS_TOTAL,
    LASPEYRES_CURRENT_INDEX,
    FISHER_CURRENT_INDEX,
    PAASCHE_CURRENT_INDEX,
    SPOT_T1_INDEX,
    CPI_TRANSPORT_IMPACT_BPS,
    CPI_HEADLINE_IMPACT_BPS,
    PIPELINE_DURATION_SECONDS,
    MODEL_TRAINING_R2,
    MODEL_TRAINING_RMSE,
)
from ..config.routes import DGCA_TOP_20_ROUTES
from ..config.db import get_db_connection
from ..scrapers.market_feed import MarketFeedGenerator, SimulationConfig
from ..pipeline.cleaner import DataCleaningPipeline
from ..engine.index_calculator import IndexCalculationEngine
from ..engine.model_trainer import train_nowcast_model
from ..services.cache import api_cache

logger = logging.getLogger("vayusutra.worker")


class IngestionWorkerDaemon:
    """
    Continuous background worker orchestrating automated scraping, MAD scrubbing,
    statutory indexing, and ML nowcast model retraining on schedule.
    """

    def __init__(self, interval_seconds: int = 60, auto_train_interval_cycles: int = 5):
        self.interval_seconds = interval_seconds
        self.auto_train_interval_cycles = auto_train_interval_cycles
        self.is_running = False
        self.is_paused = False
        self._task: Optional[asyncio.Task] = None
        self.total_cycles_executed = 0
        self.last_run_timestamp: Optional[str] = None
        self.last_duration_ms: float = 0.0
        self.last_status = "INITIAL"
        self.last_summary: Dict[str, Any] = {}

    def start(self) -> None:
        """Launches the background daemon task."""
        if self._task is None or self._task.done():
            self.is_running = True
            self.is_paused = False
            self._task = asyncio.create_task(self._run_loop())
            logger.info(f"Ingestion Worker Daemon Started (Interval: {self.interval_seconds}s)")

    def pause(self) -> None:
        """Temporarily pauses the scheduled cycles."""
        self.is_paused = True
        logger.info("Ingestion Worker Daemon Paused.")

    def resume(self) -> None:
        """Resumes scheduled cycles."""
        self.is_paused = False
        logger.info("Ingestion Worker Daemon Resumed.")

    def stop(self) -> None:
        """Stops the daemon task gracefully."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Ingestion Worker Daemon Stopped.")

    async def trigger_cycle_now(self) -> Dict[str, Any]:
        """Executes a single end-to-end ingestion and indexing cycle immediately."""
        return await self._execute_cycle()

    async def _run_loop(self) -> None:
        """Main asynchronous event loop."""
        while self.is_running:
            try:
                if not self.is_paused:
                    await self._execute_cycle()
            except Exception as e:
                logger.error(f"Error in background worker cycle: {e}")
                self.last_status = f"ERROR: {str(e)}"
            
            await asyncio.sleep(self.interval_seconds)

    async def _execute_cycle(self) -> Dict[str, Any]:
        """
        Executes end-to-end ingestion:
        1. Market feed scraping / ingestion
        2. Multi-OTA deduplication + MAD outlier rejection
        3. Jevons elementary aggregation & Laspeyres/Fisher index computation
        4. Broadcast live WebSocket ticks & update Prometheus metrics
        5. Trigger ML ensemble training every N cycles
        """
        start_time = time.monotonic()
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        booking_date = datetime.date.today()
        date_str = booking_date.isoformat()

        await stream_manager.broadcast_event(
            "INGESTION_CYCLE_START",
            {"cycle": self.total_cycles_executed + 1, "date": date_str},
            f"Starting ingestion cycle #{self.total_cycles_executed + 1} for {date_str}"
        )

        conn = get_db_connection()

        # 1. Scrape / Ingest Quotes
        feed = MarketFeedGenerator(SimulationConfig(seed=None, anomaly_rate=0.015))
        raw_quotes = feed.generate_quotes_for_date(booking_date, day_index=self.total_cycles_executed + 1)
        
        # Update metric counter
        QUOTES_INGESTED_TOTAL.labels(source_portal="AIRLINES_COMBINED", route_corridor="ALL_20_ROUTES").inc(len(raw_quotes))

        with conn:
            conn.executemany("""
                INSERT OR REPLACE INTO raw_quotes (
                    quote_id, route_code, origin, destination, airline_code, airline_name,
                    flight_number, source_portal, booking_date, travel_date, advance_window,
                    departure_time, arrival_time, base_fare, fuel_surcharge, udf, psf, asf,
                    gst, convenience_fee, total_fare, is_direct, currency, scraped_at
                ) VALUES (
                    :quote_id, :route_code, :origin, :destination, :airline_code, :airline_name,
                    :flight_number, :source_portal, :booking_date, :travel_date, :advance_window,
                    :departure_time, :arrival_time, :base_fare, :fuel_surcharge, :udf, :psf, :asf,
                    :gst, :convenience_fee, :total_fare, :is_direct, :currency, :scraped_at
                )
            """, raw_quotes)

        # 2. Clean & Outlier Rejection
        cleaner = DataCleaningPipeline()
        cleaned_quotes, clean_sum = cleaner.process_and_clean(raw_quotes)

        QUOTES_REJECTED_OUTLIERS_TOTAL.labels(filter_type="MAD_MODIFIED_Z").inc(clean_sum.outliers_flagged)

        with conn:
            cleaned_dicts = [
                {
                    "cleaned_id": c.cleaned_id,
                    "raw_quote_id": c.raw_quote_id,
                    "route_code": c.route_code,
                    "advance_window": c.advance_window,
                    "booking_date": c.booking_date,
                    "travel_date": c.travel_date,
                    "airline_code": c.airline_code,
                    "flight_number": c.flight_number,
                    "final_base_fare": c.final_base_fare,
                    "final_tax_fee": c.final_tax_fee,
                    "final_total_fare": c.final_total_fare,
                    "outlier_flag": c.outlier_flag,
                    "outlier_reason": c.outlier_reason,
                    "deduplication_kept": c.deduplication_kept,
                    "cleaned_at": c.cleaned_at,
                }
                for c in cleaned_quotes
            ]
            conn.executemany("""
                INSERT OR REPLACE INTO cleaned_quotes (
                    cleaned_id, raw_quote_id, route_code, advance_window, booking_date,
                    travel_date, airline_code, flight_number, final_base_fare, final_tax_fee,
                    final_total_fare, outlier_flag, outlier_reason, deduplication_kept, cleaned_at
                ) VALUES (
                    :cleaned_id, :raw_quote_id, :route_code, :advance_window, :booking_date,
                    :travel_date, :airline_code, :flight_number, :final_base_fare, :final_tax_fee,
                    :final_total_fare, :outlier_flag, :outlier_reason, :deduplication_kept, :cleaned_at
                )
            """, cleaned_dicts)

        # 3. Compute Elementary & National Indices
        calculator = IndexCalculationEngine()
        elem_results, relatives_map = calculator.compute_elementary_aggregates(cleaned_quotes, date_str)

        with conn:
            elem_dicts = [
                {
                    "calculation_date": e.calculation_date,
                    "route_code": e.route_code,
                    "advance_window": e.advance_window,
                    "sample_size": e.sample_size,
                    "jevons_mean_fare": e.jevons_mean_fare,
                    "base_benchmark_fare": e.base_benchmark_fare,
                    "price_relative": e.price_relative,
                    "composite_route_relative": relatives_map.get(e.route_code, {}).get(e.advance_window, 1.0),
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                for e in elem_results
            ]
            conn.executemany("""
                INSERT OR REPLACE INTO route_indices (
                    calculation_date, route_code, advance_window, sample_size,
                    jevons_mean_fare, base_benchmark_fare, price_relative,
                    composite_route_relative, created_at
                ) VALUES (
                    :calculation_date, :route_code, :advance_window, :sample_size,
                    :jevons_mean_fare, :base_benchmark_fare, :price_relative,
                    :composite_route_relative, :created_at
                )
            """, elem_dicts)

        prev_row = conn.execute("""
            SELECT laspeyres_index FROM national_indices 
            WHERE calculation_date < ? 
            ORDER BY calculation_date DESC 
            LIMIT 1
        """, (date_str,)).fetchone()
        prev_laspeyres = prev_row["laspeyres_index"] if prev_row else None

        nat_calc = calculator.compute_national_indices(
            elementary_results=elem_results,
            relatives_map=relatives_map,
            calculation_date=date_str,
            previous_laspeyres_index=prev_laspeyres,
            total_quotes=clean_sum.total_raw_quotes,
            valid_quotes=clean_sum.valid_quotes_retained,
            outliers_count=clean_sum.outliers_flagged
        )

        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO national_indices (
                    calculation_date, laspeyres_index, paasche_index, fisher_index,
                    jevons_index, spot_t1_index, daily_pct_change, bps_transport_impact,
                    bps_headline_cpi_impact, observations_count, valid_quotes_count,
                    outliers_rejected_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nat_calc.calculation_date,
                nat_calc.laspeyres_index,
                nat_calc.paasche_index,
                nat_calc.fisher_index,
                nat_calc.jevons_index,
                nat_calc.spot_t1_index,
                nat_calc.daily_pct_change,
                nat_calc.bps_transport_impact,
                nat_calc.bps_headline_cpi_impact,
                nat_calc.total_quotes_evaluated,
                nat_calc.valid_quotes_count,
                nat_calc.outliers_rejected_count,
                datetime.datetime.now(datetime.timezone.utc).isoformat()
            ))

        # 4. Update Prometheus Gauges
        LASPEYRES_CURRENT_INDEX.set(nat_calc.laspeyres_index)
        FISHER_CURRENT_INDEX.set(nat_calc.fisher_index)
        PAASCHE_CURRENT_INDEX.set(nat_calc.paasche_index)
        SPOT_T1_INDEX.set(nat_calc.spot_t1_index)
        CPI_TRANSPORT_IMPACT_BPS.set(nat_calc.bps_transport_impact)
        CPI_HEADLINE_IMPACT_BPS.set(nat_calc.bps_headline_cpi_impact)

        elapsed = time.monotonic() - start_time
        PIPELINE_DURATION_SECONDS.observe(elapsed)

        self.total_cycles_executed += 1
        self.last_run_timestamp = now_dt.isoformat()
        self.last_duration_ms = round(elapsed * 1000.0, 2)
        self.last_status = "SUCCESS"

        # 5. Optional Periodic AI Model Retraining
        if self.total_cycles_executed % self.auto_train_interval_cycles == 0:
            try:
                _, ml_metrics = train_nowcast_model()
                MODEL_TRAINING_R2.set(ml_metrics.r2_train)
                MODEL_TRAINING_RMSE.set(ml_metrics.rmse_train)
                await stream_manager.broadcast_event(
                    "MODEL_RETRAINED",
                    {"r2": ml_metrics.r2_train, "rmse": ml_metrics.rmse_train, "version": ml_metrics.model_version},
                    f"AI Nowcast Ensemble retrained: R²={ml_metrics.r2_train:.4f}"
                )
            except Exception as ml_err:
                logger.warning(f"Auto retraining note: {ml_err}")

        # 6. Broadcast Real-time Ticks to WebSocket Subscribers
        summary_payload = {
            "calculation_date": date_str,
            "master_laspeyres_index": nat_calc.laspeyres_index,
            "fisher_ideal_index": nat_calc.fisher_index,
            "spot_t1_index": nat_calc.spot_t1_index,
            "daily_pct_change": nat_calc.daily_pct_change,
            "bps_transport_impact": nat_calc.bps_transport_impact,
            "bps_headline_cpi_impact": nat_calc.bps_headline_cpi_impact,
            "raw_quotes_count": len(raw_quotes),
            "clean_quotes_indexed": clean_sum.valid_quotes_retained,
            "outliers_rejected": clean_sum.outliers_flagged,
            "cycle_number": self.total_cycles_executed,
            "duration_ms": self.last_duration_ms,
        }
        self.last_summary = summary_payload

        # Invalidate cached analytics after a new data cycle
        api_cache.clear()

        await stream_manager.broadcast_event(
            "INDEX_TICK",
            summary_payload,
            f"New APIx Index Tick: {nat_calc.laspeyres_index:.2f} (Transport: {nat_calc.bps_transport_impact:+.2f} bps)"
        )

        return summary_payload

    def get_status_report(self) -> Dict[str, Any]:
        """Returns worker telemetry."""
        return {
            "worker_daemon": "VayuSutra Autonomous Ingestion Engine",
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "interval_seconds": self.interval_seconds,
            "total_cycles_executed": self.total_cycles_executed,
            "last_run_timestamp": self.last_run_timestamp,
            "last_duration_ms": self.last_duration_ms,
            "last_status": self.last_status,
            "last_summary": self.last_summary,
        }


# Global singleton daemon
worker_daemon = IngestionWorkerDaemon(interval_seconds=60)
