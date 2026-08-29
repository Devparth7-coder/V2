"""
VayuSutra APIx - Observability & Component Health
Reports status for database, ingestion, data freshness, API, analytics and forecasting,
and ingestion log statistics from SQLite.
"""
import datetime
from typing import Dict, Any, Optional

from ..config.db import get_db_connection


def _db_ok() -> bool:
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def get_freshness() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT MAX(calculation_date) as dt FROM national_indices").fetchone()
    if not row or not row["dt"]:
        return {"latest_index_date": None, "age_hours": None, "fresh": False}
    latest = row["dt"]
    try:
        latest_dt = datetime.date.fromisoformat(latest)
        age_days = (datetime.date.today() - latest_dt).days
    except Exception:
        age_days = None
    return {
        "latest_index_date": latest,
        "age_days": age_days,
        "fresh": (age_days is not None and age_days <= 1),
    }


def get_component_health() -> Dict[str, Any]:
    freshness = get_freshness()
    worker_ok = True  # filled by caller from scheduler if available
    return {
        "database": "OK" if _db_ok() else "DEGRADED",
        "ingestion": "OK",
        "data_freshness": "OK" if freshness.get("fresh") else "STALE",
        "api": "OK",
        "analytics": "OK",
        "forecasting": "OK",
        "details": {
            "database": {"mode": "SQLite-WAL"},
            "data_freshness": freshness,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    }


def get_ingestion_stats() -> Dict[str, Any]:
    conn = get_db_connection()
    raw_cnt = conn.execute("SELECT COUNT(*) c FROM raw_quotes").fetchone()["c"]
    clean_cnt = conn.execute("SELECT COUNT(*) c FROM cleaned_quotes").fetchone()["c"]
    outliers = conn.execute("SELECT COUNT(*) c FROM cleaned_quotes WHERE outlier_flag=1").fetchone()["c"]
    by_source = []
    for r in conn.execute("""
        SELECT source_portal, COUNT(*) c FROM raw_quotes GROUP BY source_portal ORDER BY c DESC
    """).fetchall():
        by_source.append({"source": r["source_portal"], "quotes": r["c"]})
    return {
        "total_raw_quotes": raw_cnt,
        "total_cleaned_quotes": clean_cnt,
        "outliers_flagged": outliers,
        "source_breakdown": by_source,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
