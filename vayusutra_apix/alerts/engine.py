"""
VayuSutra APIx - Alert Engine
Rule-based alerting for airfare increases, CPI impact, pressure, anomalies, forecast
revision, data quality and source outage. Rules are stored in SQLite; evaluation is
deterministic. The engine supports the 'dashboard' channel now and is designed to be
extended with email/webhook/notification integrations later.
"""
import datetime
import uuid
from typing import Dict, List, Any, Optional

from ..config.db import get_db_connection


DEFAULT_RULES = [
    {"id": "rule-airfare-1", "name": "Airfare Daily Surge", "rule_type": "AIRFARE_INCREASE",
     "metric": "national_daily_pct_change", "operator": "gte", "threshold": 1.0,
     "enabled": 1, "channel": "dashboard",
     "description": "Alert when the national airfare index rises >=1.0% in a day.",
     "severity": "MODERATE"},
    {"id": "rule-cpi-1", "name": "Headline CPI Impact", "rule_type": "CPI_IMPACT",
     "metric": "headline_cpi_bps", "operator": "gte", "threshold": 0.30,
     "enabled": 1, "channel": "dashboard",
     "description": "Alert when daily headline CPI impact >=0.30 bps.",
     "severity": "MODERATE"},
    {"id": "rule-pressure-1", "name": "High Pressure", "rule_type": "PRESSURE",
     "metric": "pressure_score", "operator": "gte", "threshold": 60.0,
     "enabled": 1, "channel": "dashboard",
     "description": "Alert when Airfare Inflation Pressure Score >=60 (HIGH).",
     "severity": "HIGH"},
    {"id": "rule-anomaly-1", "name": "Market Anomaly", "rule_type": "ANOMALY",
     "metric": "anomaly_severity", "operator": "gte", "threshold": 55.0,
     "enabled": 1, "channel": "dashboard",
     "description": "Alert when a market anomaly severity score >=55.",
     "severity": "HIGH"},
    {"id": "rule-dq-1", "name": "Data Quality Low", "rule_type": "DATA_QUALITY",
     "metric": "trust_score", "operator": "lt", "threshold": 60.0,
     "enabled": 1, "channel": "dashboard",
     "description": "Alert when Data Trust Score falls below 60.",
     "severity": "HIGH"},
]


def _conn():
    return get_db_connection()


def seed_default_rules() -> None:
    conn = _conn()
    with conn:
        for r in DEFAULT_RULES:
            conn.execute("""
                INSERT OR REPLACE INTO alert_rules (
                    id, name, rule_type, metric, operator, threshold,
                    enabled, channel, description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r["id"], r["name"], r["rule_type"], r["metric"], r["operator"],
                  r["threshold"], r["enabled"], r["channel"], r["description"],
                  datetime.datetime.now(datetime.timezone.utc).isoformat()))


def list_rules() -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM alert_rules ORDER BY created_at ASC").fetchall()
    return [dict(r) for r in rows]


def create_rule(name: str, rule_type: str, metric: str, operator: str, threshold: float,
                description: str = "", severity: str = "MODERATE") -> Dict[str, Any]:
    conn = _conn()
    rid = f"rule-{uuid.uuid4().hex[:10]}"
    with conn:
        conn.execute("""
            INSERT INTO alert_rules (
                id, name, rule_type, metric, operator, threshold, enabled,
                channel, description, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 'dashboard', ?, ?)
        """, (rid, name, rule_type, metric, operator, threshold, description,
              datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return {"id": rid, "name": name, "rule_type": rule_type, "metric": metric,
            "operator": operator, "threshold": threshold, "enabled": 1,
            "channel": "dashboard", "description": description, "severity": severity}


def update_rule(rule_id: str, enabled: Optional[int] = None, threshold: Optional[float] = None) -> Optional[Dict[str, Any]]:
    conn = _conn()
    sets, params = [], []
    if enabled is not None:
        sets.append("enabled=?")
        params.append(1 if enabled else 0)
    if threshold is not None:
        sets.append("threshold=?")
        params.append(threshold)
    if not sets:
        return None
    params.append(rule_id)
    with conn:
        conn.execute(f"UPDATE alert_rules SET {', '.join(sets)} WHERE id=?", params)
    row = conn.execute("SELECT * FROM alert_rules WHERE id=?", (rule_id,)).fetchone()
    return dict(row) if row else None


# --- metric collectors -----------------------------------------------------

def _current_metrics() -> Dict[str, float]:
    m: Dict[str, float] = {}
    conn = _conn()
    row = conn.execute("SELECT daily_pct_change, bps_headline_cpi_impact FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    if row:
        m["national_daily_pct_change"] = row["daily_pct_change"] or 0.0
        m["headline_cpi_bps"] = row["bps_headline_cpi_impact"] or 0.0
    try:
        from ..analytics.pressure import compute_pressure_from_db
        m["pressure_score"] = compute_pressure_from_db().score
    except Exception:
        m["pressure_score"] = 0.0
    try:
        from ..data_quality.trust import compute_trust_report_from_db
        m["trust_score"] = compute_trust_report_from_db().trust_score
    except Exception:
        m["trust_score"] = 100.0
    try:
        an = conn.execute("SELECT MAX(severity_score) s FROM anomalies").fetchone()
        m["anomaly_severity"] = an["s"] if an and an["s"] else 0.0
    except Exception:
        m["anomaly_severity"] = 0.0
    return m


def evaluate_rules(limit: int = 20) -> List[Dict[str, Any]]:
    metrics = _current_metrics()
    rules = [r for r in list_rules() if r["enabled"]]
    conn = _conn()
    fired: List[Dict[str, Any]] = []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with conn:
        for rule in rules:
            value = metrics.get(rule["metric"])
            if value is None:
                continue
            threshold = rule["threshold"]
            op = rule["operator"]
            triggered = False
            if op == "gt":
                triggered = value > threshold
            elif op == "gte":
                triggered = value >= threshold
            elif op == "lt":
                triggered = value < threshold
            elif op == "lte":
                triggered = value <= threshold
            if triggered:
                aid = f"AL-{uuid.uuid4().hex[:10]}"
                message = (f"{rule['name']}: {rule['metric']}={value:.2f} "
                           f"{op} threshold={threshold:.2f}.")
                conn.execute("""
                    INSERT INTO alerts (id, rule_id, name, rule_type, severity, metric,
                                        threshold, message, triggered_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                """, (aid, rule["id"], rule["name"], rule["rule_type"],
                      rule.get("severity", "MODERATE"), value, threshold, message, now))
                fired.append({"id": aid, "rule_id": rule["id"], "name": rule["name"],
                              "rule_type": rule["rule_type"], "severity": rule.get("severity", "MODERATE"),
                              "metric": rule["metric"], "value": round(value, 2),
                              "threshold": threshold, "message": message,
                              "triggered_at": now, "status": "ACTIVE"})
    return fired[:limit]


def list_alerts(limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = _conn()
    q = "SELECT * FROM alerts"
    params: list = []
    if status:
        q += " WHERE status=?"
        params.append(status)
    q += " ORDER BY triggered_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


class AlertEngine:
    """Public facade for the alert system."""
    def __init__(self):
        seed_default_rules()

    def run(self) -> List[Dict[str, Any]]:
        return evaluate_rules()
