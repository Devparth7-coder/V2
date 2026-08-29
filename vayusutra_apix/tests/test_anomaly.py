"""Tests for market anomaly detection."""
import numpy as np
from vayusutra_apix.anomaly.detector import MarketAnomalyDetector


def _smooth_series(n=30, value=100.0):
    return np.full(n, value, dtype=float)


def test_detects_fare_spike():
    series = _smooth_series()
    series[-1] = 130.0  # +30% spike
    detector = MarketAnomalyDetector()
    anomalies = detector.detect(
        series_by_route={"DEL-BOM": series},
        horizon_fares={}, consensus_flags=[], national_median_change=0.0,
    )
    types = [a.anomaly_type for a in anomalies]
    assert any("SPIKE" in t for t in types)


def test_detects_horizon_inversion():
    detector = MarketAnomalyDetector()
    anomalies = detector.detect(
        series_by_route={"DEL-BOM": _smooth_series()},
        horizon_fares={"DEL-BOM": {"T+1": 4000, "T+45": 8000}},
        consensus_flags=[], national_median_change=0.0,
    )
    assert any(a.anomaly_type == "HORIZON_INVERSION" for a in anomalies)


def test_detects_route_divergence():
    flat = _smooth_series()
    spike = _smooth_series()
    spike[-1] = 125.0
    detector = MarketAnomalyDetector()
    anomalies = detector.detect(
        series_by_route={"DEL-BOM": spike, "DEL-BLR": flat},
        horizon_fares={}, consensus_flags=[], national_median_change=0.0,
    )
    assert any(a.anomaly_type == "ROUTE_DIVERGENCE" for a in anomalies)


def test_no_anomalies_on_flat_market():
    detector = MarketAnomalyDetector()
    anomalies = detector.detect(
        series_by_route={"DEL-BOM": _smooth_series(), "DEL-BLR": _smooth_series()},
        horizon_fares={"DEL-BOM": {"T+1": 5000, "T+45": 3000}},
        consensus_flags=[], national_median_change=0.0,
    )
    assert all(a.anomaly_type != "HORIZON_INVERSION" for a in anomalies)
