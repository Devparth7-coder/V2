"""
VayuSutra APIx - Forecasting Routers
National and route-level forecasts, always with confidence intervals, plus model validation.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from ...api.schemas import ForecastResponse
from ...config.routes import ROUTE_LOOKUP

router = APIRouter(prefix="/api/v1/forecast", tags=["Forecasting"])


@router.get("/national", response_model=ForecastResponse, summary="National airfare forecast")
def forecast_national(horizon_days: int = Query(7, ge=1, le=30)):
    from ...forecasting.service import get_national_forecast
    try:
        return get_national_forecast(horizon_days).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/route/{route_code}", response_model=ForecastResponse, summary="Route-level forecast")
def forecast_route(route_code: str, horizon_days: int = Query(7, ge=1, le=30)):
    if ROUTE_LOOKUP.get(route_code.upper()) is None:
        raise HTTPException(status_code=404, detail=f"Route {route_code} not in basket.")
    from ...forecasting.service import get_route_forecast
    try:
        return get_route_forecast(route_code, horizon_days).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/validation", summary="Walk-forward model validation / comparison")
def forecast_validation():
    from ...forecasting.service import run_model_validation
    return run_model_validation()


@router.get("/models", summary="List available forecasting models")
def list_models():
    from ...forecasting.models import FORECAST_MODELS
    return {"models": [m.name for m in FORECAST_MODELS()]}
