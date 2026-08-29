"""
VayuSutra APIx - Additive Schema Migration (v2)
Adds normalized tables for forecasts, anomalies, alerts, scenarios, data-quality,
source consensus, provenance and audit events. Uses CREATE TABLE IF NOT EXISTS and
guarded ALTER TABLE ADD COLUMN so the upgrade is strictly additive and never breaks
the pre-existing tables (raw_quotes, cleaned_quotes, route_indices, national_indices,
backtest_metrics) or the original insertion code paths.
"""

import logging
import sqlite3
from typing import List

logger = logging.getLogger("vayusutra.schema")

# ---------------------------------------------------------------------------
# v2 tables
# ---------------------------------------------------------------------------

V2_TABLES: List[str] = [
    # Sources registry
    """
    CREATE TABLE IF NOT EXISTS sources (
        source_portal TEXT PRIMARY KEY,
        source_type TEXT NOT NULL DEFAULT 'SIMULATED',
        is_direct INTEGER NOT NULL DEFAULT 0,
        healthy INTEGER NOT NULL DEFAULT 1,
        last_seen TEXT,
        total_quotes INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """,
    # Route metadata snapshot (mirrors config.routes for auditability)
    """
    CREATE TABLE IF NOT EXISTS routes (
        route_code TEXT PRIMARY KEY,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        origin_city TEXT NOT NULL,
        destination_city TEXT NOT NULL,
        weight REAL NOT NULL,
        distance_km INTEGER NOT NULL,
        base_fare_benchmark REAL NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    # Forecasts (national & route level) with uncertainty bands
    """
    CREATE TABLE IF NOT EXISTS forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL,                -- 'NATIONAL' | 'ROUTE'
        route_code TEXT,
        as_of_date TEXT NOT NULL,
        horizon_days INTEGER NOT NULL,
        forecast_date TEXT NOT NULL,
        model TEXT NOT NULL,
        point_forecast REAL NOT NULL,
        lower_bound REAL NOT NULL,
        upper_bound REAL NOT NULL,
        confidence_level REAL NOT NULL DEFAULT 0.95,
        metrics_json TEXT,
        data_status TEXT NOT NULL DEFAULT 'MODELLED',
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_forecasts_scope_date ON forecasts(scope, as_of_date, route_code);",
    # Market anomalies (distinct from data-quality outliers)
    """
    CREATE TABLE IF NOT EXISTS anomalies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anomaly_type TEXT NOT NULL,
        severity TEXT NOT NULL,             -- LOW | MODERATE | HIGH | CRITICAL
        severity_score REAL NOT NULL,
        route_code TEXT,
        timestamp TEXT NOT NULL,
        observed_value REAL,
        expected_lower REAL,
        expected_upper REAL,
        deviation REAL,
        confidence REAL,
        explanation TEXT,
        detected_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_anomalies_route_time ON anomalies(route_code, timestamp);",
    # Alert rules
    """
    CREATE TABLE IF NOT EXISTS alert_rules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        rule_type TEXT NOT NULL,            -- AIRFARE_INCREASE | CPI_IMPACT | PRESSURE | ANOMALY | FORECAST_REVISION | DATA_QUALITY | SOURCE_OUTAGE
        metric TEXT NOT NULL,
        operator TEXT NOT NULL,             -- gt | gte | lt | lte
        threshold REAL NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        channel TEXT NOT NULL DEFAULT 'dashboard',
        description TEXT,
        created_at TEXT NOT NULL
    );
    """,
    # Triggered alerts
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        rule_id TEXT,
        name TEXT NOT NULL,
        rule_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        metric REAL,
        threshold REAL,
        message TEXT,
        triggered_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(triggered_at);",
    # Scenario simulation runs
    """
    CREATE TABLE IF NOT EXISTS scenario_runs (
        id TEXT PRIMARY KEY,
        scenario_name TEXT,
        params_json TEXT NOT NULL,
        results_json TEXT NOT NULL,
        pressure_score REAL,
        pressure_level TEXT,
        projected_cpi_bps REAL,
        data_status TEXT NOT NULL DEFAULT 'MODELLED',
        created_at TEXT NOT NULL
    );
    """,
    # Data quality / trust snapshots
    """
    CREATE TABLE IF NOT EXISTS data_quality_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date TEXT NOT NULL,
        trust_score REAL NOT NULL,
        components_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    # Audit events / provenance trail
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        route_code TEXT,
        source_portal TEXT,
        request_id TEXT,
        detail TEXT,
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);",
    # Index snapshots (historical national index for lineage)
    """
    CREATE TABLE IF NOT EXISTS index_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calculation_date TEXT NOT NULL,
        laspeyres_index REAL NOT NULL,
        fisher_index REAL NOT NULL,
        bps_headline_cpi_impact REAL NOT NULL,
        data_status TEXT NOT NULL DEFAULT 'SIMULATED',
        source_signature TEXT,
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_index_snapshots_date ON index_snapshots(calculation_date);",
]

# ---------------------------------------------------------------------------
# guarded column additions
# ---------------------------------------------------------------------------

RAW_QUOTE_COLUMNS = {
    "scraper_version": "TEXT DEFAULT '1.0.0'",
    "source_type": "TEXT DEFAULT 'SIMULATED'",
    "data_status": "TEXT DEFAULT 'SIMULATED'",
    "consensus_status": "TEXT DEFAULT 'NORMAL'",
    "source_health": "REAL DEFAULT 1.0",
}

CLEANED_QUOTE_COLUMNS = {
    "data_status": "TEXT DEFAULT 'SIMULATED'",
    "source_consensus": "TEXT DEFAULT 'NORMAL'",
}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def migrate_v2(conn: sqlite3.Connection) -> None:
    """Apply all additive v2 schema changes idempotently on an existing connection."""
    for stmt in V2_TABLES:
        conn.execute(stmt)

    # Guarded provenance columns on raw_quotes
    for col, ddl in RAW_QUOTE_COLUMNS.items():
        _add_column_if_missing(conn, "raw_quotes", col, ddl)
    for col, ddl in CLEANED_QUOTE_COLUMNS.items():
        _add_column_if_missing(conn, "cleaned_quotes", col, ddl)

    conn.commit()
    logger.info("v2 schema migration applied.")


def apply_migration() -> None:
    """Convenience wrapper that migrates the global DB connection."""
    from ..config.db import get_db_connection
    conn = get_db_connection()
    migrate_v2(conn)
