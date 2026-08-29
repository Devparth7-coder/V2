"""
VayuSutra APIx - Market Anomaly Routers
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from ...config.routes import ROUTE_LOOKUP

router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomalies"])


@router.get("", response_model=List[Dict[str, Any]], summary="Detected market anomalies")
def list_or_detect_anomalies(recompute: bool = Query(False),
                             route_code: Optional[str] = Query(None),
                             limit: int = Query(50, ge=1, le=200)):
    from ...anomaly.detector import get_anomalies_from_db, detect_anomalies_from_db
    if route_code and ROUTE_LOOKUP.get(route_code.upper()) is None:
        raise HTTPException(status_code=404, detail=f"Route {route_code} not in basket.")
    if recompute:
        detect_anomalies_from_db(route_code=route_code)
    return get_anomalies_from_db(route_code=route_code, limit=limit)


@router.get("/route/{route_code}", summary="Anomalies for a specific route")
def route_anomalies(route_code: str, limit: int = Query(50)):
    if ROUTE_LOOKUP.get(route_code.upper()) is None:
        raise HTTPException(status_code=404, detail=f"Route {route_code} not in basket.")
    from ...anomaly.detector import get_anomalies_from_db
    return get_anomalies_from_db(route_code=route_code, limit=limit)
