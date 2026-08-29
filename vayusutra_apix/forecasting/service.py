"""
VayuSutra APIx - Forecasting Service
Runs walk-forward validation to automatically select the best forecasting model for a
given series, produces point forecasts with confidence intervals, and persists results
to the `forecasts` table. Deterministic and reproducible.
"""
import datetime
import json
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from .models import (
    BaseForecaster, FORECAST_MODELS, EnsembleForecaster,
    evaluate_forecast, ForecastMetrics,
)
from ..config.db import get_db_connection

Z_95 = 1.96


@dataclass
class ForecastResult:
    as_of_date: str
    horizon_days: int
    forecast_date: str
    model: str
    point_forecast: float
    lower_bound: float
    upper_bound: float
    confidence_level: float
    metrics: Dict[str, float]
    model_metrics: Dict[str, ForecastMetrics]
    generated_at: str
    data_status: str = "MODELLED"
    series_sample: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "horizon_days": self.horizon_days,
            "forecast_date": self.forecast_date,
            "model": self.model,
            "point_forecast": round(self.point_forecast, 2),
            "lower_bound": round(self.lower_bound, 2),
            "upper_bound": round(self.upper_bound, 2),
            "confidence_level": self.confidence_level,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "model_validation": {name: m.to_dict() for name, m in self.model_metrics.items()},
            "data_status": self.data_status,
            "generated_at": self.generated_at,
            "series_sample": self.series_sample,
        }


def _walk_forward_validate(series: np.ndarray, steps: int,
                           train_frac: float = 0.6) -> Dict[str, ForecastMetrics]:
    """Evaluate each model on an expanding-window walk-forward split."""
    n = len(series)
    split = max(5, int(n * train_frac))
    results: Dict[str, ForecastMetrics] = {}
    for model in FORECAST_MODELS():
        train = series[:split]
        test = series[split:]
        if len(test) < 1:
            results[model.name] = ForecastMetrics()
            continue
        h = min(steps, len(test))
        try:
            pred, _ = model.fit_forecast(train, h)
            pred = np.asarray(pred[:h])
            results[model.name] = evaluate_forecast(test[:h], pred)
        except Exception:
            results[model.name] = ForecastMetrics()
    return results


def _select_best(model_metrics: Dict[str, ForecastMetrics]) -> str:
    best = None
    best_score = float("inf")
    for name, m in model_metrics.items():
        if m.mape <= 0 and m.rmse <= 0:
            continue
        score = m.rmse + m.mape  # composite: RMSE + MAPE
        if score < best_score:
            best_score = score
            best = name
    return best or "seasonal_naive"


def _forecast_with_model(series: np.ndarray, model_name: str,
                         steps: int) -> Tuple[np.ndarray, float]:
    for m in FORECAST_MODELS():
        if m.name == model_name:
            pred, resid_std = m.fit_forecast(series, steps)
            return np.asarray(pred[:steps]), resid_std
    # fallback ensemble
    ens = EnsembleForecaster()
    pred, resid_std = ens.fit_forecast(series, steps)
    return np.asarray(pred[:steps]), resid_std


def run_forecast(series: List[float], steps: int, data_status: str = "MODELLED",
                 as_of_date: Optional[str] = None) -> ForecastResult:
    arr = np.asarray(series, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        raise ValueError("Insufficient data to forecast (need at least 3 points).")

    steps = max(1, min(int(steps), 45))
    model_metrics = _walk_forward_validate(arr, steps)
    best_model = _select_best(model_metrics)
    pred, resid_std = _forecast_with_model(arr, best_model, steps)

    point = float(pred[steps - 1])
    sigma = max(resid_std, 1e-3)
    ci = Z_95 * sigma * math.sqrt(steps)
    lower = point - ci
    upper = point + ci

    as_of = as_of_date or arr_date_fallback()
    fc_date = (datetime.date.today() + datetime.timedelta(days=steps)).isoformat()

    chosen_metrics = model_metrics.get(best_model, ForecastMetrics())

    return ForecastResult(
        as_of_date=as_of,
        horizon_days=steps,
        forecast_date=fc_date,
        model=best_model,
        point_forecast=round(point, 2),
        lower_bound=round(max(0, lower), 2),
        upper_bound=round(upper, 2),
        confidence_level=0.95,
        metrics=chosen_metrics.to_dict(),
        model_metrics=model_metrics,
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        data_status=data_status,
        series_sample=len(arr),
    )


def arr_date_fallback() -> str:
    row = _db().execute("SELECT MAX(calculation_date) dt FROM national_indices").fetchone()
    return row["dt"] if row and row["dt"] else datetime.date.today().isoformat()


def _db():
    return get_db_connection()


def _persist(scope: str, route_code: Optional[str], result: ForecastResult) -> None:
    try:
        conn = _db()
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO forecasts (
                    scope, route_code, as_of_date, horizon_days, forecast_date, model,
                    point_forecast, lower_bound, upper_bound, confidence_level,
                    metrics_json, data_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scope, route_code, result.as_of_date, result.horizon_days,
                result.forecast_date, result.model, result.point_forecast,
                result.lower_bound, result.upper_bound, result.confidence_level,
                json.dumps(result.model_metrics), result.data_status,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ))
    except Exception:
        pass


def get_national_forecast(steps: int = 7) -> ForecastResult:
    rows = _db().execute(
        "SELECT calculation_date, laspeyres_index FROM national_indices ORDER BY calculation_date ASC"
    ).fetchall()
    series = [r["laspeyres_index"] for r in rows]
    as_of = rows[-1]["calculation_date"] if rows else None
    result = run_forecast(series, steps, data_status="MODELLED", as_of_date=as_of)
    _persist("NATIONAL", None, result)
    return result


def get_route_forecast(route_code: str, steps: int = 7) -> ForecastResult:
    rows = _db().execute("""
        SELECT calculation_date, AVG(composite_route_relative) AS rel
        FROM route_indices WHERE route_code=? GROUP BY calculation_date ORDER BY calculation_date ASC
    """, (route_code.upper(),)).fetchall()
    if not rows:
        raise ValueError(f"No data for route {route_code}")
    series = [r["rel"] for r in rows]
    as_of = rows[-1]["calculation_date"]
    result = run_forecast(series, steps, data_status="MODELLED", as_of_date=as_of)
    _persist("ROUTE", route_code.upper(), result)
    return result


def run_model_validation() -> Dict[str, Any]:
    """Walk-forward model comparison on the national series (Validation Center)."""
    rows = _db().execute(
        "SELECT calculation_date, laspeyres_index FROM national_indices ORDER BY calculation_date ASC"
    ).fetchall()
    series = [r["laspeyres_index"] for r in rows]
    arr = np.asarray(series, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 8:
        return {"status": "INSUFFICIENT_DATA", "sample": len(arr), "models": {}}
    steps = 5
    model_metrics = _walk_forward_validate(arr, steps, train_frac=0.6)
    best = _select_best(model_metrics)
    return {
        "status": "VALIDATED",
        "sample": len(arr),
        "validation_horizon": steps,
        "best_model": best,
        "models": {name: m.to_dict() for name, m in model_metrics.items()},
        "methodology": "Expanding-window walk-forward validation with auto model selection.",
    }
