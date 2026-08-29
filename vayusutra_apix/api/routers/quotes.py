"""
VayuSutra APIx - Quote Provenance / Audit Trail Routers
Enables drill-down from index -> route -> observations -> source -> raw quote.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/quotes", tags=["Quotes / Provenance"])


@router.get("", summary="List quotes with provenance metadata")
def list_quotes(route_code: Optional[str] = Query(None), source_portal: Optional[str] = Query(None),
                limit: int = Query(50, ge=1, le=500)):
    from ...config.db import get_db_connection
    conn = get_db_connection()
    q = """SELECT quote_id, route_code, airline_code, flight_number, source_portal,
                  booking_date, travel_date, advance_window, total_fare,
                  scraper_version, source_type, data_status, consensus_status
           FROM raw_quotes"""
    conds, params = [], []
    if route_code:
        conds.append("route_code=?")
        params.append(route_code.upper())
    if source_portal:
        conds.append("source_portal=?")
        params.append(source_portal)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY scraped_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    return {"count": len(rows), "quotes": [dict(r) for r in rows]}


@router.get("/{quote_id}", summary="Full provenance record for a quote")
def get_quote(quote_id: str):
    from ...config.db import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM raw_quotes WHERE quote_id=?", (quote_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found.")
    data = dict(row)

    # Lineage: find cleaned record derived from this raw quote
    cleaned = conn.execute(
        "SELECT * FROM cleaned_quotes WHERE raw_quote_id=?", (quote_id,)).fetchone()
    lineage = {}
    if cleaned:
        lineage["cleaned"] = dict(cleaned)
    else:
        lineage["cleaned"] = "No cleaned record (rejected or not processed)."

    return {
        "quote": data,
        "provenance": {
            "traceable": True,
            "source_portal": data.get("source_portal"),
            "source_type": data.get("source_type", "SIMULATED"),
            "scraper_version": data.get("scraper_version", "1.0.0"),
            "validation_status": "SCHEMA_VALIDATED",
            "cleaning_status": "CLEANED" if cleaned else "NOT_CLEANED",
            "data_status": data.get("data_status", "SIMULATED"),
        },
        "lineage": lineage,
    }
