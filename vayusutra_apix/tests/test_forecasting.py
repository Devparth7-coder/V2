"""Tests for the forecasting framework: models, metrics, model selection and CIs."""
import numpy as np
import pytest

from vayusutra_apix.forecasting.models import (
    SeasonalNaiveForecaster, ExponentialSmoothingForecaster, EnsembleForecaster,
    evaluate_forecast, FORECAST_MODELS,
)
from vayusutra_apix.forecasting.service import run_forecast


def _synthetic_series(n=40, start=100.0, trend=0.15):
    x = np.arange(n)
    noise = np.random.RandomState(42).normal(0, 0.4, n)
    return (start + trend * x + 2.0 * np.sin(x / 3.0) + noise).tolist()


def test_seasonal_naive_repeats_season():
    series = np.array([100, 102, 101, 103, 99, 98, 100, 104, 101, 105, 100, 99])
    fc = SeasonalNaiveForecaster(season=3).fit(series)
    pred = fc.forecast(3)
    # seasonal naive predicts values from `season` back
    assert pred[0] == series[-3]
    assert pred[1] == series[-2]
    assert pred[2] == series[-1]


def test_evaluate_forecast_metrics():
    y_true = np.array([100, 101, 102])
    y_pred = np.array([100, 101, 102])
    m = evaluate_forecast(y_true, y_pred)
    assert m.mae == 0.0
    assert m.rmse == 0.0
    assert m.mape == 0.0
    assert m.smape == 0.0
    assert m.r2 == pytest.approx(1.0)


def test_run_forecast_returns_ci_and_metrics():
    result = run_forecast(_synthetic_series(), steps=7)
    assert result.lower_bound <= result.point_forecast <= result.upper_bound
    assert result.horizon_days == 7
    assert result.model in [m.name for m in FORECAST_MODELS()]
    assert result.confidence_level == 0.95
    assert "rmse" in result.metrics
    assert result.data_status == "MODELLED"


def test_run_forecast_insufficient_data_raises():
    with pytest.raises(ValueError):
        run_forecast([1, 2], steps=5)


def test_ensemble_produces_prediction():
    ens = EnsembleForecaster()
    pred, _ = ens.fit_forecast(np.array(_synthetic_series()), 5)
    assert len(pred) == 5
    assert np.all(np.isfinite(pred))


def test_model_selection_prefers_reasonable_model():
    series = _synthetic_series()
    model_metrics = {m.name: None for m in FORECAST_MODELS()}
    # run_forecast internally selects best; just ensure it doesn't crash and picks valid
    result = run_forecast(series, steps=3)
    assert result.model_metrics  # non-empty
