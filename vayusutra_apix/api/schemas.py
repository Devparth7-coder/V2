"""VayuSutra APIx - Pydantic response schemas for the v1 API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ForecastResponse(BaseModel):
    as_of_date: str
    horizon_days: int
    forecast_date: str
    model: str
    point_forecast: float
    lower_bound: float
    upper_bound: float
    confidence_level: float
    metrics: Dict[str, Any]
    model_validation: Dict[str, Any]
    data_status: str
    generated_at: str


class AnomalyResponse(BaseModel):
    anomaly_type: str
    severity: str
    severity_score: float
    route_code: Optional[str]
    timestamp: str
    observed_value: Optional[float]
    expected_range: Dict[str, Optional[float]]
    deviation: Optional[float]
    confidence: float
    explanation: str


class ScenarioInputModel(BaseModel):
    airfare_shock_pct: float = 0.0
    demand_change_pct: float = 0.0
    capacity_change_pct: float = 0.0
    atf_adjustment_pct: float = 0.0
    booking_horizon_shock_pct: float = 0.0
    seasonal_factor_pct: float = 0.0
    name: str = "Custom scenario"


class AlertRuleModel(BaseModel):
    name: str
    rule_type: str
    metric: str
    operator: str
    threshold: float
    description: str = ""
    severity: str = "MODERATE"


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    components: Dict[str, str]
    telemetry: Dict[str, Any]
    timestamp: str
