"""
VayuSutra APIx - Market Anomaly Detection
Detects unusual MARKET behaviour (distinct from data-quality outliers):
  - sudden fare spikes / drops (rolling z-score + EWMA)
  - unusual route divergence
  - booking-horizon inversion
  - source disagreement

Each anomaly reports severity, route, timestamp, observed value, expected range, deviation,
confidence and an explanation. Deterministic.
"""
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import numpy as np

from ..config.routes import DGCA_TOP_20_ROUTES, ADVANCE_PURCHASE_WINDOWS
from ..config.db import get_db_connection


@dataclass
class MarketAnomaly:
    anomaly_type: str
    severity: str
    severity_score: float
    route_code: Optional[str]
    timestamp: str
    observed_value: Optional[float]
    expected_lower: Optional[float]
    expected_upper: Optional[float]
    deviation: Optional[float]
    confidence: float
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "severity_score": round(self.severity_score, 2),
            "route_code": self.route_code,
            "timestamp": self.timestamp,
            "observed_value": self.observed_value,
            "expected_range": {"lower": round(self.expected_lower, 2) if self.expected_lower is not None else None,
                               "upper": round(self.expected_upper, 2) if self.expected_upper is not None else None},
            "deviation": round(self.deviation, 2) if self.deviation is not None else None,
            "confidence": round(self.confidence, 2),
            "explanation": self.explanation,
        }


def _severity_for(z: float) -> tuple:
    az = abs(z)
    if az >= 5:
        return "CRITICAL", 90
    if az >= 4:
        return "HIGH", 75
    if az >= 3:
        return "MODERATE", 55
    return "LOW", 35


class MarketAnomalyDetector:
    def __init__(self, z_threshold: float = 2.5, ewma_alpha: float = 0.2):
        self.z_threshold = z_threshold
        self.ewma_alpha = ewma_alpha

    def _rolling_z(self, series: np.ndarray, window: int = 7) -> np.ndarray:
        if len(series) < window + 1:
            return np.zeros(len(series))
        zs = np.zeros(len(series))
        for i in range(len(series)):
            lo = max(0, i - window + 1)
            seg = series[lo:i]  # exclude current
            if i == 0 or len(seg) < 3:
                continue
            mean = float(np.mean(seg))
            std = float(np.std(seg)) + 1e-9
            zs[i] = (series[i] - mean) / std
        return zs

    def _ewma(self, series: np.ndarray) -> np.ndarray:
        out = np.zeros(len(series))
        out[0] = series[0]
        for i in range(1, len(series)):
            out[i] = self.ewma_alpha * series[i] + (1 - self.ewma_alpha) * out[i - 1]
        return out

    def detect(self, series_by_route: Dict[str, np.ndarray],
               horizon_fares: Dict[str, Dict[str, float]],
               consensus_flags: List[Dict[str, Any]],
               national_median_change: float) -> List[MarketAnomaly]:
        anomalies: List[MarketAnomaly] = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Fare spikes/drops (z-score + EWMA) on composite relative series
        for route, series in series_by_route.items():
            if len(series) < 5:
                continue
            arr = np.asarray(series, dtype=float)
            zs = self._rolling_z(arr)
            ew = self._ewma(arr)
            last_z = zs[-1]
            last_ewma = ew[-1]
            # EWMA deviation
            ew_dev = (arr[-1] - last_ewma) / (last_ewma + 1e-9) * 100.0
            if abs(last_z) >= self.z_threshold or abs(ew_dev) >= 8.0:
                typ = "SPIKE" if arr[-1] > np.mean(arr) else "DROP"
                sev, score = _severity_for(last_z)
                std = float(np.std(arr)) + 1e-9
                anomalies.append(MarketAnomaly(
                    anomaly_type=f"FARE_{typ}", severity=sev, severity_score=score,
                    route_code=route, timestamp=now,
                    observed_value=float(arr[-1]),
                    expected_lower=float(np.mean(arr) - 1.96 * std),
                    expected_upper=float(np.mean(arr) + 1.96 * std),
                    deviation=float((arr[-1] - np.mean(arr)) / np.mean(arr) * 100.0),
                    confidence=float(min(1.0, abs(last_z) / 6.0)),
                    explanation=f"Route {route} composite relative {arr[-1]:.4f} deviates "
                                f"({(arr[-1]-np.mean(arr))/np.mean(arr)*100.0:+.1f}%) from its recent "
                                f"rolling mean; z={last_z:.2f}.",
                ))

        # 2. Route divergence from national median daily change
        for route in series_by_route:
            series = np.asarray(series_by_route[route], dtype=float)
            if len(series) < 2:
                continue
            chg = ((series[-1] - series[-2]) / series[-2] * 100.0) if series[-2] > 0 else 0.0
            if abs(chg) >= 5.0 and abs(chg - national_median_change) >= 4.0:
                anomalies.append(MarketAnomaly(
                    anomaly_type="ROUTE_DIVERGENCE", severity="MODERATE", severity_score=55,
                    route_code=route, timestamp=now, observed_value=round(chg, 2),
                    expected_lower=None, expected_upper=None, deviation=round(chg, 2),
                    confidence=0.7,
                    explanation=f"Route {route} moved {chg:+.2f}% in 24h vs national median "
                                f"{national_median_change:+.2f}%, indicating unusual divergence.",
                ))

        # 3. Booking-horizon inversion (T+1 should exceed T+45)
        for route, hf in horizon_fares.items():
            t1 = hf.get("T+1")
            t45 = hf.get("T+45")
            if t1 and t45 and t1 > 0 and t45 > 0 and t1 < t45 * 0.85:
                anomalies.append(MarketAnomaly(
                    anomaly_type="HORIZON_INVERSION", severity="MODERATE", severity_score=60,
                    route_code=route, timestamp=now,
                    observed_value=float(t1),
                    expected_lower=None, expected_upper=float(t45),
                    deviation=float((t1 - t45) / t45 * 100.0),
                    confidence=0.75,
                    explanation=f"Route {route} shows inverted yield: T+1 ({t1:.0f}) below T+45 "
                                f"({t45:.0f}), contradicting normal advance-purchase pricing.",
                ))

        # 4. Source disagreement
        for cf in consensus_flags:
            if cf.get("level") == "HIGH DISAGREEMENT":
                anomalies.append(MarketAnomaly(
                    anomaly_type="SOURCE_DISAGREEMENT", severity="WARNING", severity_score=50,
                    route_code=cf.get("route_code"), timestamp=now,
                    observed_value=round(cf.get("cv", 0.0), 4),
                    expected_lower=None, expected_upper=None,
                    deviation=round(cf.get("cv", 0.0), 4), confidence=0.8,
                    explanation="Sources disagree substantially (coefficient of variation "
                                f"{cf.get('cv',0):.3f}) on route {cf.get('route_code')}; flagged for review, "
                                "not deleted.",
                ))

        return anomalies


def _persist(anomalies: List[MarketAnomaly]) -> None:
    conn = get_db_connection()
    with conn:
        for a in anomalies:
            conn.execute("""
                INSERT INTO anomalies (
                    anomaly_type, severity, severity_score, route_code, timestamp,
                    observed_value, expected_lower, expected_upper, deviation,
                    confidence, explanation, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (a.anomaly_type, a.severity, a.severity_score, a.route_code, a.timestamp,
                  a.observed_value, a.expected_lower, a.expected_upper, a.deviation,
                  a.confidence, a.explanation,
                  datetime.datetime.now(datetime.timezone.utc).isoformat()))


def detect_anomalies_from_db(route_code: Optional[str] = None,
                             persist: bool = True) -> List[MarketAnomaly]:
    conn = get_db_connection()
    # Build per-route composite relative series
    series_by_route: Dict[str, np.ndarray] = {}
    for r in DGCA_TOP_20_ROUTES:
        rows = conn.execute("""
            SELECT calculation_date, AVG(composite_route_relative) rel
            FROM route_indices WHERE route_code=? GROUP BY calculation_date ORDER BY calculation_date ASC
        """, (r.route_code,)).fetchall()
        series_by_route[r.route_code] = np.array([row["rel"] for row in rows], dtype=float)

    # Horizon fares (latest)
    latest = conn.execute("SELECT MAX(calculation_date) dt FROM route_indices").fetchone()
    horizon_fares: Dict[str, Dict[str, float]] = {}
    if latest and latest["dt"]:
        for row in conn.execute("""
            SELECT route_code, advance_window, jevons_mean_fare FROM route_indices WHERE calculation_date=?
        """, (latest["dt"],)).fetchall():
            horizon_fares.setdefault(row["route_code"], {})[row["advance_window"]] = row["jevons_mean_fare"]

    # Source consensus flags
    consensus_flags = []
    try:
        from ..analytics.consensus import ConsensusEngine, compute_source_consensus_from_db
        for cc in compute_source_consensus_from_db():
            consensus_flags.append({"route_code": cc.route_code if hasattr(cc, 'route_code') else None,
                                    "level": cc.level, "cv": cc.cv})
    except Exception:
        consensus_flags = []

    # National median daily change
    changes = []
    for route, s in series_by_route.items():
        if len(s) >= 2 and s[-2] > 0:
            changes.append((s[-1] - s[-2]) / s[-2] * 100.0)
    national_median_change = float(np.median(changes)) if changes else 0.0

    detector = MarketAnomalyDetector()
    anomalies = detector.detect(series_by_route, horizon_fares, consensus_flags, national_median_change)

    if route_code:
        anomalies = [a for a in anomalies if a.route_code == route_code.upper()]
    if persist:
        _persist(anomalies)
    return anomalies


def get_anomalies_from_db(route_code: Optional[str] = None,
                          limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    q = """
        SELECT anomaly_type, severity, severity_score, route_code, timestamp,
               observed_value, expected_lower, expected_upper, deviation, confidence, explanation
        FROM anomalies
    """
    params: list = []
    if route_code:
        q += " WHERE route_code=?"
        params.append(route_code.upper())
    q += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]
