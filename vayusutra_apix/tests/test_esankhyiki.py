"""
VayuSutra APIx - MoSPI eSankhyiki Integration Test Suite
Verifies connectivity models, CPI group codes, baseline series, and macro transmission projections
for https://esankhyiki.mospi.gov.in.
"""

import pytest
from fastapi.testclient import TestClient
from vayusutra_apix.scrapers.esankhyiki_connector import ESankhyikiConnector
from vayusutra_apix.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_esankhyiki_connector_metadata():
    """Verify eSankhyiki connector returns statutory MoSPI classification codes."""
    connector = ESankhyikiConnector()
    meta = connector.get_cpi_metadata()
    assert meta["source_portal"] == "eSankhyiki - Ministry of Statistics and Programme Implementation"
    assert meta["monitored_group"]["group_code"] == "6.1.03"
    assert meta["monitored_group"]["group_name"] == "Transport and communication"
    assert meta["monitored_group"]["weights"]["combined"] == 8.59
    assert meta["monitored_group"]["weights"]["rural"] == 7.60
    assert meta["monitored_group"]["weights"]["urban"] == 9.73


def test_esankhyiki_historical_baseline():
    """Verify historical monthly eSankhyiki published baseline series."""
    connector = ESankhyikiConnector()
    baseline = connector.fetch_historical_baseline()
    assert len(baseline) >= 12
    assert "transport_combined" in baseline[0]
    assert "headline_cpi" in baseline[0]


def test_esankhyiki_augmented_projection():
    """Verify mathematical transmission into eSankhyiki monthly indices."""
    connector = ESankhyikiConnector()
    # Test +10% airfare increase
    proj = connector.compute_augmented_cpi_projection(current_apix_value=110.0, base_apix_value=100.0)
    assert proj["esankhyiki_official_baseline"]["transport_combined_index"] > 0
    assert proj["augmented_nowcast_cpi"]["augmented_transport_index"] > proj["esankhyiki_official_baseline"]["transport_combined_index"]
    assert proj["augmented_nowcast_cpi"]["transport_impact_bps"] > 0
    assert proj["augmented_nowcast_cpi"]["headline_cpi_impact_bps"] > 0


def test_esankhyiki_api_endpoints(client):
    """Verify all eSankhyiki REST API endpoints return HTTP 200 and expected schemas."""
    # 1. Metadata
    r_meta = client.get("/api/v1/esankhyiki/metadata")
    assert r_meta.status_code == 200
    assert r_meta.json()["monitored_group"]["group_code"] == "6.1.03"

    # 2. Baseline
    r_base = client.get("/api/v1/esankhyiki/cpi-baseline")
    assert r_base.status_code == 200
    assert r_base.json()["group_code"] == "6.1.03"

    # 3. Augmented CPI
    r_aug = client.get("/api/v1/esankhyiki/augmented-cpi")
    assert r_aug.status_code == 200
    assert "augmented_nowcast_cpi" in r_aug.json()

    # 4. Sync
    r_sync = client.post("/api/v1/esankhyiki/sync")
    assert r_sync.status_code == 200
    assert r_sync.json()["status"] == "SYNCED"
