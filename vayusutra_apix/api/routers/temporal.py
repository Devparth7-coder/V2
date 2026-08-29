"""
VayuSutra APIx - Advanced Temporal Analytics Routers
"""
from fastapi import APIRouter
from ...services.cache import api_cache

router = APIRouter(prefix="/api/v1/analytics/temporal", tags=["Temporal Analytics"])


@router.get("", summary="Weekday, horizon and route temporal patterns")
def get_temporal():
    from ...analytics.temporal import build_temporal_analytics_from_db
    return api_cache.get_or_compute("temporal", build_temporal_analytics_from_db, ttl_seconds=120)
