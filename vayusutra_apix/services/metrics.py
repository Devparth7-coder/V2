"""
VayuSutra APIx - Prometheus Metrics & Microservice Observability Service
Exposes OpenMetrics counters, gauges, histograms, and hardware telemetry for MoSPI & RBI IT infrastructure.
"""

import time
import psutil
from typing import Dict, Any
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    REGISTRY,
)

# Standard Prometheus Metric Declarations
QUOTES_INGESTED_TOTAL = Counter(
    "apix_quotes_ingested_total",
    "Total raw flight quotes ingested from all airlines and OTAs",
    ["source_portal", "route_corridor"]
)

QUOTES_REJECTED_OUTLIERS_TOTAL = Counter(
    "apix_quotes_rejected_outliers_total",
    "Total flight quotes rejected by MAD modified Z-score or sub-statutory filters",
    ["filter_type"]
)

LASPEYRES_CURRENT_INDEX = Gauge(
    "apix_laspeyres_current_index",
    "Current Master Laspeyres Airfare Price Index value (Base 2026=100)"
)

FISHER_CURRENT_INDEX = Gauge(
    "apix_fisher_current_index",
    "Current Superlative Fisher Ideal Index value"
)

PAASCHE_CURRENT_INDEX = Gauge(
    "apix_paasche_current_index",
    "Current Paasche Airfare Price Index value"
)

SPOT_T1_INDEX = Gauge(
    "apix_spot_t1_index",
    "Current Spot Emergency T+1 Sub-Index value"
)

CPI_TRANSPORT_IMPACT_BPS = Gauge(
    "apix_cpi_transport_impact_bps",
    "Current Basis Point (bps) impact on MoSPI CPI Transport & Communication Group 6.1.03"
)

CPI_HEADLINE_IMPACT_BPS = Gauge(
    "apix_cpi_headline_impact_bps",
    "Current Basis Point (bps) impact on All-India Headline CPI"
)

PIPELINE_DURATION_SECONDS = Histogram(
    "apix_pipeline_duration_seconds",
    "Execution duration of end-to-end ingestion, cleaning, and index calculation cycle",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

MODEL_TRAINING_R2 = Gauge(
    "apix_model_training_r2",
    "Latest validation R-squared score of the ML Nowcast Ensemble"
)

MODEL_TRAINING_RMSE = Gauge(
    "apix_model_training_rmse",
    "Latest Root Mean Squared Error of the ML Nowcast Ensemble"
)

SYSTEM_CPU_PERCENT = Gauge(
    "apix_system_cpu_percent",
    "Current server CPU utilization percentage"
)

SYSTEM_MEMORY_MB = Gauge(
    "apix_system_memory_mb",
    "Current server RAM consumption in Megabytes"
)

ACTIVE_WEBSOCKET_CLIENTS = Gauge(
    "apix_active_websocket_clients",
    "Current active WebSocket live streaming clients connected"
)


def update_system_gauges():
    """Refreshes hardware and memory metrics."""
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().used / (1024 * 1024)
        SYSTEM_CPU_PERCENT.set(cpu)
        SYSTEM_MEMORY_MB.set(mem)
    except Exception:
        pass


def get_prometheus_metrics_payload() -> tuple[bytes, str]:
    """Generates OpenMetrics formatted byte buffer."""
    update_system_gauges()
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
