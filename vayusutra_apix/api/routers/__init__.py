"""VayuSutra APIx - v1 Routers (organized by domain)."""

from .analytics import router as analytics_router
from .forecast import router as forecast_router
from .anomalies import router as anomalies_router
from .scenario import router as scenario_router
from .data_quality import router as data_quality_router
from .alerts import router as alerts_router
from .reports import router as reports_router
from .quotes import router as quotes_router
from .ai import router as ai_router
from .temporal import router as temporal_router

__all__ = [
    "analytics_router", "forecast_router", "anomalies_router", "scenario_router",
    "data_quality_router", "alerts_router", "reports_router", "quotes_router",
    "ai_router", "temporal_router",
]
