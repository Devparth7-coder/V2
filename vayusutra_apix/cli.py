"""
VayuSutra APIx - Command-Line Interface (CLI) Management Tool
Enterprise DevOps operations, data ingestion, ML model training, and worker controls.
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
import uvicorn

from .config.db import init_db
from .engine.backtest import DGCABacktestEngine
from .engine.model_trainer import train_nowcast_model
from .engine.nowcast_predictor import InflationNowcastPredictor
from .scrapers.esankhyiki_connector import ESankhyikiConnector
from .services.scheduler import IngestionWorkerDaemon


def cmd_serve(args):
    """Start the production FastAPI web service."""
    print(f"[*] Starting VayuSutra APIx Production Service on {args.host}:{args.port} (Workers: {args.workers})...")
    uvicorn.run("vayusutra_apix.api.main:app", host=args.host, port=args.port, workers=args.workers)


def cmd_ingest(args):
    """Execute live/simulated scraping, MAD cleaning, and index calculation."""
    init_db()
    from .scrapers.market_feed import MarketFeedGenerator, SimulationConfig
    from .pipeline.cleaner import DataCleaningPipeline
    from .engine.index_calculator import IndexCalculationEngine
    from .config.db import get_db_connection

    date_str = args.date or datetime.date.today().isoformat()
    booking_date = datetime.date.fromisoformat(date_str)
    
    print(f"[*] Executing Ingestion Cycle for {date_str}...")
    feed = MarketFeedGenerator(SimulationConfig(seed=None, anomaly_rate=0.015))
    raw_quotes = feed.generate_quotes_for_date(booking_date, day_index=1)
    
    cleaner = DataCleaningPipeline()
    cleaned_quotes, clean_sum = cleaner.process_and_clean(raw_quotes)

    calculator = IndexCalculationEngine()
    elem_results, relatives_map = calculator.compute_elementary_aggregates(cleaned_quotes, date_str)
    nat_calc = calculator.compute_national_indices(elem_results, relatives_map, date_str)

    print(f"[+] Ingestion Complete:")
    print(f"    - Raw Quotes Ingested: {clean_sum.total_raw_quotes}")
    print(f"    - Multi-OTA Duplicates Dropped: {clean_sum.duplicates_dropped}")
    print(f"    - MAD Outliers Filtered: {clean_sum.outliers_flagged}")
    print(f"    - Clean Quotes Indexed: {clean_sum.valid_quotes_retained}")
    print(f"    - Master Laspeyres Index: {nat_calc.laspeyres_index:.2f}")
    print(f"    - Fisher Ideal Index: {nat_calc.fisher_index:.2f}")
    print(f"    - Transport Sub-Group Impact: {nat_calc.bps_transport_impact:+.2f} bps")
    print(f"    - Headline CPI Impact: {nat_calc.bps_headline_cpi_impact:+.4f} bps")


def cmd_train(args):
    """Train the econometric nowcast ML model."""
    init_db()
    print("[*] Training Econometric Nowcast Ensemble (Ridge + GBDT)...")
    ensemble, metrics = train_nowcast_model()
    print("[+] Model Training Successful!")
    print(f"    - Model Version: {metrics.model_version}")
    print(f"    - Training R²: {metrics.r2_train:.4f}")
    print(f"    - Validation Pearson r: {metrics.pearson_r:.4f}")
    print(f"    - Test RMSE: {metrics.rmse_test:.4f}")
    print(f"    - Test MAPE: {metrics.mape_test:.2f}%")
    print(f"    - Total Observations Evaluated: {metrics.sample_size}")
    print(f"    - Top Drivers: {list(metrics.feature_importances.keys())[:4]}")


def cmd_nowcast(args):
    """Run forward nowcast prediction."""
    init_db()
    print(f"[*] Generating {args.horizon}-Day Forward Nowcast...")
    predictor = InflationNowcastPredictor()
    report = predictor.generate_nowcast(horizon_days=args.horizon)
    print(f"[+] Forward Nowcast Output (As of {report.as_of_date}):")
    print(f"    - Current Index: {report.current_index}")
    print(f"    - Mean Horizon Index: {report.summary_mean_forecast}")
    print(f"    - Projected Transport CPI Impact: {report.net_projected_transport_bps:+.2f} bps")
    print(f"    - Projected Headline CPI Impact: {report.net_projected_headline_cpi_bps:+.4f} bps")
    print(f"    - RBI Monetary Policy Stance: {report.monetary_policy_alert}")


def cmd_backtest(args):
    """Run DGCA 30-Day statistical backtest validation."""
    init_db()
    print(f"[*] Running DGCA Backtest Validation over {args.days} Days...")
    engine = DGCABacktestEngine()
    res = engine.run_backtest(num_days=args.days)
    print(f"[+] Backtest Validation Report:")
    print(f"    - Pearson Correlation r: {res.pearson_r:.4f} (Mandate >0.85)")
    print(f"    - MAPE vs DGCA Yield: {res.mape:.2f}% (Mandate <4.0%)")
    print(f"    - RMSE: {res.rmse:.2f}")
    print(f"    - R²: {res.r2:.4f} (Mandate >0.75)")
    print(f"    - Status: {res.validation_status}")
    print(f"    - Report Exported To: {res.report_path}")


def cmd_sync_esankhyiki(args):
    """Synchronize with official MoSPI eSankhyiki catalog."""
    print("[*] Connecting to eSankhyiki (https://esankhyiki.mospi.gov.in)...")
    connector = ESankhyikiConnector()
    meta = connector.get_cpi_metadata()
    baseline = connector.fetch_historical_baseline()
    proj = connector.compute_augmented_cpi_projection(current_apix_value=105.5)
    print(f"[+] eSankhyiki Data Synchronized:")
    print(f"    - Group Code: {meta['monitored_group']['group_code']} ({meta['monitored_group']['group_name']})")
    print(f"    - Combined Weight: {meta['monitored_group']['weights']['combined']}%")
    print(f"    - Monthly Baseline Records: {len(baseline)}")
    print(f"    - Policy Implication: {proj['policy_implication']}")


def cmd_worker(args):
    """Run autonomous background ingestion daemon."""
    init_db()
    print(f"[*] Launching Standalone Ingestion Worker Daemon (Interval: {args.interval}s)...")
    daemon = IngestionWorkerDaemon(interval_seconds=args.interval)
    daemon.start()

    async def main_loop():
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            daemon.stop()
            print("\n[*] Daemon terminated gracefully.")

    asyncio.run(main_loop())


def main():
    parser = argparse.ArgumentParser(
        prog="vayusutra",
        description="VayuSutra APIx - Real-Time Airfare Price Index & Macro Econometric CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # serve
    p_serve = subparsers.add_parser("serve", help="Start FastAPI production server")
    p_serve.add_argument("--host", default="0.0.0.0", help="Binding host IP (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    p_serve.add_argument("--workers", type=int, default=1, help="Worker processes (default: 1)")
    p_serve.set_defaults(func=cmd_serve)

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Run on-demand ingestion and calculation")
    p_ingest.add_argument("--date", help="Optional YYYY-MM-DD date")
    p_ingest.set_defaults(func=cmd_ingest)

    # train
    p_train = subparsers.add_parser("train", help="Train AI Nowcast ML Ensemble")
    p_train.set_defaults(func=cmd_train)

    # nowcast
    p_nowcast = subparsers.add_parser("nowcast", help="Generate forward inflation nowcast")
    p_nowcast.add_argument("--horizon", type=int, default=14, help="Forecast horizon in days")
    p_nowcast.set_defaults(func=cmd_nowcast)

    # backtest
    p_backtest = subparsers.add_parser("backtest", help="Run 35-day DGCA backtest validation")
    p_backtest.add_argument("--days", type=int, default=35, help="Number of days to backtest")
    p_backtest.set_defaults(func=cmd_backtest)

    # sync-esankhyiki
    p_sync = subparsers.add_parser("sync-esankhyiki", help="Sync with MoSPI eSankhyiki catalog")
    p_sync.set_defaults(func=cmd_sync_esankhyiki)

    # worker
    p_worker = subparsers.add_parser("worker", help="Run autonomous worker daemon")
    p_worker.add_argument("--interval", type=int, default=60, help="Cycle interval in seconds")
    p_worker.set_defaults(func=cmd_worker)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
