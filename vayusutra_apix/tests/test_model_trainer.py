"""
VayuSutra APIx - Machine Learning Model Training & Nowcasting Test Suite
Verifies feature engineering, model training convergence, persistence, multi-horizon forecasting,
and FastAPI ML endpoints.
"""

import os
import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from vayusutra_apix.engine.model_trainer import (
    FeatureEngineer,
    EconometricNowcastEnsemble,
    train_nowcast_model,
    MODEL_ARTIFACT_PATH,
)
from vayusutra_apix.engine.nowcast_predictor import InflationNowcastPredictor
from vayusutra_apix.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_feature_engineering():
    """Verify feature matrix generation with valid lag and cyclical columns."""
    dates = pd.date_range("2026-07-01", periods=25, freq="D")
    df = pd.DataFrame({
        "calculation_date": dates.strftime("%Y-%m-%d"),
        "laspeyres_index": 100.0 + np.sin(np.arange(25)) * 5.0,
        "fisher_index": 100.0 + np.sin(np.arange(25)) * 4.9,
        "paasche_index": 100.0 + np.sin(np.arange(25)) * 4.8,
        "spot_t1_index": 240.0 + np.sin(np.arange(25)) * 10.0,
        "daily_pct_change": np.random.normal(0, 0.5, 25),
        "bps_transport_impact": np.random.normal(0, 1.0, 25),
        "bps_headline_cpi_impact": np.random.normal(0, 0.1, 25),
        "observations_count": [900] * 25,
        "valid_quotes_count": [850] * 25,
        "outliers_rejected_count": [50] * 25,
    })

    X, y = FeatureEngineer.build_feature_dataframe(df)
    assert len(X) > 0
    assert len(y) == len(X)
    assert "lag_1_laspeyres" in X.columns
    assert "rolling_mean_7d" in X.columns
    assert "day_of_week_sin" in X.columns
    assert "spot_t1_spread_ratio" in X.columns


def test_model_training_and_serialization():
    """Verify ensemble training, evaluation metric calculation, and disk persistence."""
    ensemble, metrics = train_nowcast_model()
    assert ensemble.is_trained is True
    assert metrics.r2_train > 0.80
    assert metrics.pearson_r > 0.85
    assert metrics.rmse_test < 6.0
    assert metrics.mape_test < 5.0
    assert os.path.exists(MODEL_ARTIFACT_PATH)

    # Test loading from disk
    loaded_model = EconometricNowcastEnsemble.load(MODEL_ARTIFACT_PATH)
    assert loaded_model.is_trained is True


def test_nowcast_prediction_pipeline():
    """Verify multi-horizon forward nowcast generation and confidence interval boundaries."""
    predictor = InflationNowcastPredictor()
    report = predictor.generate_nowcast(horizon_days=7)
    
    assert report.forecast_horizon_days == 7
    assert len(report.forecast_steps) == 7
    for step in report.forecast_steps:
        assert step.confidence_interval_95_lower <= step.predicted_laspeyres_index
        assert step.predicted_laspeyres_index <= step.confidence_interval_95_upper
        assert step.predicted_laspeyres_index > 0


def test_model_api_endpoints(client):
    """Verify REST API model training, status, and prediction endpoints."""
    # 1. Train endpoint
    r_train = client.post("/api/v1/model/train")
    assert r_train.status_code == 200
    data_tr = r_train.json()
    assert data_tr["status"] == "SUCCESS"
    assert "metrics" in data_tr

    # 2. Status endpoint
    r_status = client.get("/api/v1/model/status")
    assert r_status.status_code == 200
    data_st = r_status.json()
    assert data_st["status"] == "READY_PRODUCTION"
    assert "feature_importances" in data_st

    # 3. Predict endpoint
    r_pred = client.get("/api/v1/model/predict?horizon_days=14")
    assert r_pred.status_code == 200
    data_pr = r_pred.json()
    assert data_pr["forecast_horizon_days"] == 14
    assert len(data_pr["forecast_trajectory"]) == 14
    assert "projected_cpi_impact" in data_pr
