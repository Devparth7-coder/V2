"""
VayuSutra APIx - Alert Engine Routers
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from ...api.schemas import AlertRuleModel

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


@router.get("", summary="Triggered alerts")
def get_alerts(status: Optional[str] = Query(None), limit: int = Query(50)):
    from ...alerts.engine import list_alerts
    return list_alerts(limit=limit, status=status)


@router.get("/rules", summary="Configured alert rules")
def get_rules():
    from ...alerts.engine import list_rules
    return list_rules()


@router.post("/rules", summary="Create an alert rule")
def post_rule(rule: AlertRuleModel):
    from ...alerts.engine import create_rule
    return create_rule(name=rule.name, rule_type=rule.rule_type, metric=rule.metric,
                       operator=rule.operator, threshold=rule.threshold,
                       description=rule.description, severity=rule.severity)


@router.patch("/rules/{rule_id}", summary="Update an alert rule")
def patch_rule(rule_id: str, enabled: Optional[int] = Query(None),
               threshold: Optional[float] = Query(None)):
    from ...alerts.engine import update_rule
    result = update_rule(rule_id, enabled=enabled, threshold=threshold)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found.")
    return result


@router.post("/evaluate", summary="Evaluate rules against current state")
def evaluate():
    from ...alerts.engine import evaluate_rules
    return {"fired": evaluate_rules()}
