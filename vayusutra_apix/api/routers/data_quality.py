"""
VayuSutra APIx - Data Quality / Trust Center Routers
"""
from fastapi import APIRouter
from ...services.cache import api_cache

router = APIRouter(prefix="/api/v1/data-quality", tags=["Data Quality"])


@router.get("", summary="Data Trust Score & components")
def get_data_quality():
    from ...data_quality.trust import compute_trust_report_from_db
    return compute_trust_report_from_db().to_dict()


@router.get("/components", summary="Detailed trust components")
def get_components():
    from ...data_quality.trust import compute_trust_report_from_db
    return compute_trust_report_from_db().components.to_dict()
