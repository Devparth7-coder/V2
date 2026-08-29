"""
VayuSutra APIx - FastAPI Integration Test Suite
Verifies all REST API endpoints for HTTP 200 responses, schema validity, and execution.
"""

import pytest
from fastapi.testclient import TestClient
from vayusutra_apix.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_dashboard_endpoint(client):
    """GET / returns HTML dashboard."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "VAYUSUTRA APIx" in response.text


def test_health_endpoint(client):
    """GET /api/v1/health returns system health telemetry."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "telemetry" in data
    assert data["telemetry"]["dgca_routes_monitored"] == 20


def test_realtime_index_endpoint(client):
    """GET /api/v1/index/realtime returns latest index data."""
    response = client.get("/api/v1/index/realtime")
    assert response.status_code == 200
    data = response.json()
    assert "master_laspeyres_index" in data
    assert "fisher_ideal_index" in data
    assert "cpi_transmission" in data
    assert data["cpi_transmission"]["transport_cpi_weight_pct"] == 8.59


def test_timeseries_endpoint(client):
    """GET /api/v1/index/timeseries returns historical daily records."""
    response = client.get("/api/v1/index/timeseries?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0
    assert "laspeyres_index" in data["data"][0]


def test_routes_endpoint(client):
    """GET /api/v1/routes returns all 20 DGCA routes with valid weights."""
    response = client.get("/api/v1/routes")
    assert response.status_code == 200
    data = response.json()
    assert data["total_routes"] == 20
    assert pytest.approx(data["total_weight"], 1e-4) == 1.0


def test_elasticity_endpoint(client):
    """GET /api/v1/analytics/elasticity returns 5 advance purchase horizons."""
    response = client.get("/api/v1/analytics/elasticity")
    assert response.status_code == 200
    data = response.json()
    assert len(data["windows"]) == 5
    window_ids = [w["window_id"] for w in data["windows"]]
    assert window_ids == ["T+1", "T+7", "T+15", "T+30", "T+45"]


def test_cpi_impact_matrix(client):
    """GET /api/v1/analytics/cpi-impact returns sensitivity scenarios."""
    response = client.get("/api/v1/analytics/cpi-impact")
    assert response.status_code == 200
    data = response.json()
    assert "sensitivity_stress_matrix" in data
    assert len(data["sensitivity_stress_matrix"]) > 0


def test_backtest_endpoint(client):
    """GET /api/v1/backtest returns econometric validation metrics."""
    response = client.get("/api/v1/backtest")
    assert response.status_code == 200
    data = response.json()
    assert "pearson_r" in data
    assert "mape" in data
    assert data["pearson_r"] >= 0.80
    assert data["mape"] <= 4.5


def test_ingest_run_endpoint(client):
    """POST /api/v1/ingest/run executes live ingestion pipeline."""
    response = client.post("/api/v1/ingest/run?custom_date_str=2026-08-26")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "ingestion_summary" in data
    assert "computed_indices" in data


def test_export_csv_endpoint(client):
    """GET /api/v1/export/csv returns downloadable CSV stream."""
    response = client.get("/api/v1/export/csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "Calculation_Date" in response.text
    assert "Laspeyres_Airfare_Index" in response.text


def test_actual_datasets_endpoints(client):
    """Verify actual dataset endpoints for MoSPI CPI, DGCA traffic, and quotes."""
    # 1. MoSPI CPI
    r_cpi = client.get("/api/v1/datasets/mospi-cpi")
    assert r_cpi.status_code == 200
    assert r_cpi.json()["count"] > 20

    # 2. DGCA Traffic
    r_dgca = client.get("/api/v1/datasets/dgca-traffic")
    assert r_dgca.status_code == 200
    assert r_dgca.json()["count"] == 20

    # 3. Live Flight Quotes
    r_quotes = client.get("/api/v1/datasets/flight-quotes?limit=10")
    assert r_quotes.status_code == 200
    assert "quotes" in r_quotes.json()


def test_live_fare_decomposer_calculator(client):
    """Verify live fare decomposition and basis-point CPI calculation."""
    r_calc = client.post("/api/v1/calculator/decompose?route_code=DEL-BOM&base_plus_fuel_fare=6800")
    assert r_calc.status_code == 200
    data = r_calc.json()
    assert data["statutory_price_decomposition"]["total_gross_fare_payable_inr"] == 7851.0
    assert "transport_subgroup_impact_bps" in data["econometric_cpi_transmission"]


def test_superlative_and_regional_endpoints(client):
    """Verify superlative comparison, regional breakdown, and cryptographic audit vault."""
    # 1. Superlative Matrix
    r_sup = client.get("/api/v1/index/superlative")
    assert r_sup.status_code == 200
    data_sup = r_sup.json()
    assert "superlative_matrix" in data_sup
    assert "fisher_ideal_superlative_index" in data_sup["superlative_matrix"]

    # 2. Regional Breakdown
    r_reg = client.get("/api/v1/index/regional")
    assert r_reg.status_code == 200
    data_reg = r_reg.json()
    assert "regional_hubs" in data_reg
    assert "delhi_ncr_corridor" in data_reg["regional_hubs"]

    # 3. Cryptographic Provenance
    r_aud = client.get("/api/v1/audit/provenance")
    assert r_aud.status_code == 200
    data_aud = r_aud.json()
    assert "cryptographic_hash_sha256" in data_aud
    assert data_aud["provenance_status"] == "TAMPER_PROOF_VALIDATED"
