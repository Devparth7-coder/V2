"""
VayuSutra APIx - Forecasting Models
Deterministic, reproducible forecasting models for the daily airfare index series:
Seasonal Naive, Exponential Smoothing (ETS), SARIMA (optional), Gradient Boosting and an
Ensemble. Every model exposes `fit`/`forecast` and residual standard error for CIs.
"""
import datetime
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class ForecastMetrics:
    mae: float = 0.0
    rmse: float = 0.0
    mape: float = 0.0
    smape: float = 0.0
    r2: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mae": round(self.mae, 4), "rmse": round(self.rmse, 4),
            "mape": round(self.mape, 3), "smape": round(self.smape, 3),
            "r2": round(self.r2, 4),
        }


def evaluate_forecast(y_true: np.ndarray, y_pred: np.ndarray) -> ForecastMetrics:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.maximum(1e-6, y_true))) * 100.0)
    smape = float(np.mean(2 * np.abs(y_true - y_pred) / (np.abs(y_true) + np.abs(y_pred) + 1e-9)) * 100.0)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return ForecastMetrics(mae=mae, rmse=rmse, mape=mape, smape=smape, r2=r2)


# ---------------------------------------------------------------------------
# Base forecaster
# ---------------------------------------------------------------------------

class BaseForecaster:
    name = "base"

    def __init__(self):
        self.residual_std = 1.0
        self._fitted = False

    def fit(self, series: np.ndarray) -> "BaseForecaster":
        self._fitted = True
        return self

    def forecast(self, steps: int) -> np.ndarray:
        raise NotImplementedError

    def fit_forecast(self, series: np.ndarray, steps: int) -> Tuple[np.ndarray, float]:
        self.fit(series)
        pred = self.forecast(steps)
        # residual std from in-sample one-step naive errors
        err = series[1:] - series[:-1]
        self.residual_std = float(np.std(err)) if len(err) > 1 else 1.0
        return pred, self.residual_std


class SeasonalNaiveForecaster(BaseForecaster):
    """Forecast = value from `season` days ago (weekly seasonality default)."""
    name = "seasonal_naive"

    def __init__(self, season: int = 7):
        super().__init__()
        self.season = season
        self._series: Optional[np.ndarray] = None

    def fit(self, series: np.ndarray):
        self._series = np.asarray(series, dtype=float)
        super().fit(self._series)
        return self

    def forecast(self, steps: int) -> np.ndarray:
        s = self._series
        out = []
        for i in range(steps):
            idx = len(s) - self.season + i
            out.append(s[idx] if 0 <= idx < len(s) else s[-1])
        return np.array(out)


class ExponentialSmoothingForecaster(BaseForecaster):
    """
    ETS via statsmodels (Holt, if data long enough) with graceful fallback to a
    simple exponential smoothing + drift implementation.
    """
    name = "ets"

    def __init__(self, alpha: float = 0.3):
        super().__init__()
        self.alpha = alpha
        self._level = 0.0
        self._trend = 0.0
        self._has_trend = False

    def fit(self, series: np.ndarray):
        s = np.asarray(series, dtype=float)
        try:
            from statsmodels.tsa.holtwinters import SimpleExpSmoothing, Holt
            if len(s) >= 6:
                model = Holt(s, damped_trend=True).fit(optimized=True)
                self._level = float(model.level[-1])
                self._trend = float(model.trend[-1])
                self._has_trend = True
            else:
                model = SimpleExpSmoothing(s).fit(optimized=True)
                self._level = float(model.level[-1])
                self._trend = 0.0
                self._has_trend = False
        except Exception:
            # manual SES + linear trend
            self._level = float(s[-1])
            if len(s) >= 2:
                self._trend = float(s[-1] - s[-2])
                self._has_trend = len(s) >= 5
            else:
                self._trend = 0.0
        super().fit(s)
        return self

    def forecast(self, steps: int) -> np.ndarray:
        out = []
        for i in range(1, steps + 1):
            if self._has_trend:
                out.append(self._level + self._trend * i)
            else:
                out.append(self._level)
        return np.array(out)


class SARIMAForecaster(BaseForecaster):
    """SARIMA via statsmodels, small order, with try/except fallback to seasonal naive."""
    name = "sarima"

    def __init__(self, order=(1, 0, 0), seasonal_order=(0, 0, 0, 7)):
        super().__init__()
        self.order = order
        self.seasonal_order = seasonal_order
        self._series = None

    def fit(self, series: np.ndarray):
        s = np.asarray(series, dtype=float)
        self._series = s
        super().fit(s)
        return self

    def forecast(self, steps: int) -> np.ndarray:
        s = self._series
        try:
            from statsmodels.tsa.statespace.sarimax import SARIMAX
            so = self.seasonal_order if len(s) >= 14 else (0, 0, 0, 0)
            model = SARIMAX(s, order=self.order, seasonal_order=so,
                            enforce_stationarity=False, enforce_invertibility=False)
            fit = model.fit(disp=False, maxiter=200)
            return np.asarray(fit.forecast(steps), dtype=float)
        except Exception:
            # fallback: seasonal naive + drift
            out = []
            base = s[-1]
            drift = (s[-1] - s[0]) / max(1, len(s) - 1) if len(s) > 1 else 0.0
            for i in range(steps):
                out.append(base + drift * (i + 1))
            return np.array(out)


class GradientBoostForecaster(BaseForecaster):
    """Gradient boosting regression on lag features; only used when data is sufficient."""
    name = "gradient_boosting"

    def __init__(self, lags: int = 5, random_state: int = 42):
        super().__init__()
        self.lags = lags
        self.random_state = random_state
        self._model = None
        self._last = None

    def fit(self, series: np.ndarray):
        s = np.asarray(series, dtype=float)
        self._last = s
        if len(s) >= self.lags + 4:
            from sklearn.ensemble import GradientBoostingRegressor
            X, y = self._lagged(s)
            self._model = GradientBoostingRegressor(
                n_estimators=80, max_depth=2, learning_rate=0.05,
                random_state=self.random_state).fit(X, y)
        super().fit(s)
        return self

    def _lagged(self, s):
        X, y = [], []
        for i in range(self.lags, len(s)):
            X.append(s[i - self.lags:i])
            y.append(s[i])
        return np.array(X), np.array(y)

    def forecast(self, steps: int) -> np.ndarray:
        if self._model is None:
            # fallback drift
            s = self._last
            base = s[-1]
            drift = (s[-1] - s[0]) / max(1, len(s) - 1)
            return np.array([base + drift * (i + 1) for i in range(steps)])
        s = self._last
        window = list(s[-self.lags:])
        out = []
        for _ in range(steps):
            pred = float(self._model.predict([window])[0])
            out.append(pred)
            window = window[1:] + [pred]
        return np.array(out)


class EnsembleForecaster(BaseForecaster):
    """Weighted average of component forecasters (equal weights by default)."""
    name = "ensemble"

    def __init__(self, models: Optional[List[BaseForecaster]] = None):
        super().__init__()
        self.models = models if models is not None else [
            SeasonalNaiveForecaster(season=7),
            ExponentialSmoothingForecaster(),
            SARIMAForecaster(),
        ]
        self._residuals = []

    def fit(self, series: np.ndarray):
        s = np.asarray(series, dtype=float)
        for m in self.models:
            m.fit(s)
        super().fit(s)
        return self

    def forecast(self, steps: int) -> np.ndarray:
        preds = np.array([m.forecast(steps) for m in self.models])
        return np.mean(preds, axis=0)

    def fit_forecast(self, series: np.ndarray, steps: int):
        pred, _ = super().fit_forecast(series, steps)
        err = series[1:] - series[:-1]
        self.residual_std = float(np.std(err)) if len(err) > 1 else 1.0
        return pred, self.residual_std


def FORECAST_MODELS() -> List[BaseForecaster]:
    return [
        SeasonalNaiveForecaster(season=7),
        ExponentialSmoothingForecaster(),
        SARIMAForecaster(),
        GradientBoostForecaster(),
    ]
