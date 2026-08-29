"""Integration tests for the upgraded v2 API endpoints."""
import pytest
from fastapi.testclient import TestClient
from vayusutra_apix.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_has_components(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "HEALTHY"
    assert "components" in data
    assert data["telemetry"]["dgca_routes_monitored"] == 20


def test_timeseries_returns_most_recent_window(client):
    """
    Regression: /api/v1/index/timeseries must return the MOST RECENT `limit` days in
    ascending chronological order (not the OLDEST), so the dashboard graph tracks the
    latest ingested data instead of being frozen on the first `limit` days.
    """
    full = client.get("/api/v1/index/timeseries?limit=365").json()["data"]
    assert len(full) > 2
    latest_date = full[-1]["calculation_date"]
    win = client.get("/api/v1/index/timeseries?limit=3").json()["data"]
    # Limited window must end at the latest available date and be ascending.
    assert win[-1]["calculation_date"] == latest_date
    dates = [r["calculation_date"] for r in win]
    assert dates == sorted(dates)


def test_overview_endpoint(client):
    r = client.get("/api/v1/analytics/overview")
    assert r.status_code == 200
    d = r.json()
    assert "kpi" in d and "heatmap" in d
    assert d["kpi"]["active_routes"] <= 20
    assert d["data_status"] == "SIMULATED"


def test_heatmap_shape(client):
    r = client.get("/api/v1/analytics/heatmap")
    assert r.status_code == 200
    d = r.json()
    assert len(d["routes"]) == 20
    assert len(d["windows"]) == 5
    assert len(d["cells"]) == 100


def test_pressure_score(client):
    r = client.get("/api/v1/analytics/pressure")
    assert r.status_code == 200
    d = r.json()
    assert "pressure_score" in d and "level" in d
    assert 0 <= d["pressure_score"] <= 100
    assert d["level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert "drivers" in d


def test_cpi_decomposition(client):
    r = client.get("/api/v1/analytics/cpi-decomposition")
    assert r.status_code == 200
    d = r.json()
    assert len(d["contributors"]) == 20
    assert abs(d["total_contributions_sum_bps"] - d["headline_cpi_impact_bps"]) < 1e-6


def test_forecast_national_has_ci(client):
    r = client.get("/api/v1/forecast/national?horizon_days=7")
    assert r.status_code == 200
    d = r.json()
    assert d["lower_bound"] <= d["point_forecast"] <= d["upper_bound"]
    assert d["data_status"] == "MODELLED"
    assert "rmse" in d["metrics"]


def test_forecast_route_unknown_404(client):
    r = client.get("/api/v1/forecast/route/XXX-YYY")
    assert r.status_code == 404


def test_forecast_route_known(client):
    r = client.get("/api/v1/forecast/route/DEL-BOM?horizon_days=3")
    assert r.status_code == 200
    assert r.json()["point_forecast"] > 0


def test_validation_endpoint(client):
    r = client.get("/api/v1/forecast/validation")
    assert r.status_code == 200
    d = r.json()
    assert "models" in d and "best_model" in d


def test_anomalies_endpoint(client):
    r = client.get("/api/v1/anomalies?recompute=true&limit=20")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_data_quality_endpoint(client):
    r = client.get("/api/v1/data-quality")
    assert r.status_code == 200
    d = r.json()
    assert 0 <= d["trust_score"] <= 100
    assert "components" in d


def test_scenario_simulate(client):
    r = client.post("/api/v1/scenario/simulate",
                    json={"airfare_shock_pct": 10, "demand_change_pct": 5, "capacity_change_pct": -3})
    assert r.status_code == 200
    d = r.json()
    assert d["projected_index_change_pct"] > 0
    assert d["data_status"] == "MODELLED"
    assert "confidence_range" in d


def test_scenario_invalid_input_422(client):
    r = client.post("/api/v1/scenario/simulate", json={"airfare_shock_pct": "not-a-number"})
    assert r.status_code == 422


def test_ai_analyst_grounded(client):
    r = client.post("/api/v1/ai/ask", json={"question": "Which routes contributed most to CPI pressure?"})
    assert r.status_code == 200
    d = r.json()
    assert "answer" in d and "intent" in d
    assert d["intent"] == "cpi_contributors"
    assert d["affected_routes"]


def test_ai_analyst_empty_question_422(client):
    r = client.post("/api/v1/ai/ask", json={"question": ""})
    assert r.status_code == 422


def test_quote_provenance(client):
    quotes = client.get("/api/v1/quotes?limit=1").json()
    if quotes["count"] == 0:
        pytest.skip("No quotes in DB")
    qid = quotes["quotes"][0]["quote_id"]
    r = client.get(f"/api/v1/quotes/{qid}")
    assert r.status_code == 200
    d = r.json()
    assert d["quote"]["quote_id"] == qid
    assert "provenance" in d and "lineage" in d


def test_alerts_crud(client):
    # list rules
    rules = client.get("/api/v1/alerts/rules")
    assert rules.status_code == 200
    # create
    r = client.post("/api/v1/alerts/rules", json={
        "name": "Test rule", "rule_type": "PRESSURE", "metric": "pressure_score",
        "operator": "gte", "threshold": 90, "description": "test", "severity": "HIGH"})
    assert r.status_code == 200
    rid = r.json()["id"]
    # patch
    pr = client.patch(f"/api/v1/alerts/rules/{rid}?enabled=0")
    assert pr.status_code == 200
    assert pr.json()["enabled"] == 0
    # evaluate
    ev = client.post("/api/v1/alerts/evaluate")
    assert ev.status_code == 200


def test_reports_daily(client):
    r = client.get("/api/v1/reports/daily")
    assert r.status_code == 200
    d = r.json()
    assert "national_index" in d and "pressure_score" in d and "data_quality" in d


def test_source_analytics_no_fabricated_share(client):
    r = client.get("/api/v1/analytics/source-analytics")
    assert r.status_code == 200
    d = r.json()
    for a in d["airlines"]:
        # market_share is either a number (official DGCA) or None
        assert a["market_share"] is None or isinstance(a["market_share"], float)
    assert "market_share_note" in d


def test_route_intelligence_404(client):
    assert client.get("/api/v1/analytics/route/NOPE-NOPE").status_code == 404


def test_route_intelligence_200(client):
    r = client.get("/api/v1/analytics/route/DEL-BOM")
    assert r.status_code == 200
    d = r.json()
    assert d["route_code"] == "DEL-BOM"
    assert "horizons" in d and "changes" in d
