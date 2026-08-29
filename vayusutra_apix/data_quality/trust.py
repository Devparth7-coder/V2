"""
VayuSutra APIx - Data Trust Center
Computes a transparent, weighted DATA TRUST SCORE (0-100) from objective components:
freshness, completeness, route coverage, source availability, duplicate rate,
outlier rate, validation success and source agreement.

Weights are explicit and documented (see `DEFAULT_COMPONENT_WEIGHTS`); they sum to 1.0.
The calculation is deterministic and reproducible given the same inputs.
"""
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from ..config.routes import DGCA_TOP_20_ROUTES, ADVANCE_PURCHASE_WINDOWS


# ---------------------------------------------------------------------------
# Documented component weights (sum to 1.0)
# ---------------------------------------------------------------------------
DEFAULT_COMPONENT_WEIGHTS: Dict[str, float] = {
    "freshness": 0.18,
    "completeness": 0.16,
    "coverage": 0.14,
    "source_availability": 0.12,
    "duplicate_rate": 0.10,
    "outlier_rate": 0.12,
    "validation_success": 0.08,
    "source_agreement": 0.10,
}

EXPECTED_SOURCE_PORTALS = [
    "DIRECT_INDIGO", "DIRECT_AIRINDIA", "DIRECT_SPICEJET", "DIRECT_AKASAAIR",
    "OTA_MAKEMYTRIP", "OTA_EASEMYTRIP", "OTA_CLEARTRIP",
]


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


@dataclass
class TrustComponents:
    freshness: float = 0.0
    completeness: float = 0.0
    coverage: float = 0.0
    source_availability: float = 0.0
    duplicate_rate: float = 0.0        # raw percentage (0-100)
    outlier_rate: float = 0.0          # raw percentage (0-100)
    validation_success: float = 0.0
    source_agreement: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "freshness": round(self.freshness, 1),
            "completeness": round(self.completeness, 1),
            "coverage": round(self.coverage, 1),
            "source_availability": round(self.source_availability, 1),
            "duplicate_rate": round(self.duplicate_rate, 2),
            "outlier_rate": round(self.outlier_rate, 2),
            "validation_success": round(self.validation_success, 1),
            "source_agreement": round(self.source_agreement, 1),
        }


@dataclass
class TrustReport:
    trust_score: float
    level: str
    components: TrustComponents
    weights: Dict[str, float]
    data_status: str = "SIMULATED"
    computed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        comps = self.components.to_dict()
        # Component sub-scores (inverse of bad rates) used in the weighted average
        sub = {
            "freshness": comps["freshness"],
            "completeness": comps["completeness"],
            "coverage": comps["coverage"],
            "source_availability": comps["source_availability"],
            "duplicate_rate": _clamp(100.0 - comps["duplicate_rate"] * 10.0),
            "outlier_rate": _clamp(100.0 - comps["outlier_rate"] * 8.0),
            "validation_success": comps["validation_success"],
            "source_agreement": comps["source_agreement"],
        }
        return {
            "trust_score": round(self.trust_score, 1),
            "level": self.level,
            "data_status": self.data_status,
            "computed_at": self.computed_at,
            "components": comps,
            "component_sub_scores": {k: round(v, 1) for k, v in sub.items()},
            "weights": self.weights,
        }


class DataTrustCalculator:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = dict(weights or DEFAULT_COMPONENT_WEIGHTS)
        assert abs(sum(self.weights.values()) - 1.0) < 1e-6, "Trust weights must sum to 1.0"

    @staticmethod
    def _freshness_subscore(age_days: Optional[int]) -> float:
        if age_days is None:
            return 0.0
        if age_days <= 1:
            return 100.0
        return _clamp(100.0 - (age_days - 1) * 20.0)

    def compute(self, *, age_days: Optional[int], present_cells: int,
                total_cells: int, routes_present: int, total_routes: int,
                sources_seen: int, total_sources: int, duplicate_rate: float,
                outlier_rate: float, validation_score: float, source_agreement: float,
                data_status: str = "SIMULATED") -> TrustReport:
        components = TrustComponents(
            freshness=self._freshness_subscore(age_days),
            completeness=_clamp((present_cells / max(1, total_cells)) * 100.0),
            coverage=_clamp((routes_present / max(1, total_routes)) * 100.0),
            source_availability=_clamp((sources_seen / max(1, total_sources)) * 100.0),
            duplicate_rate=duplicate_rate,
            outlier_rate=outlier_rate,
            validation_success=_clamp(validation_score),
            source_agreement=_clamp(source_agreement),
        )
        sub = {
            "freshness": components.freshness,
            "completeness": components.completeness,
            "coverage": components.coverage,
            "source_availability": components.source_availability,
            "duplicate_rate": _clamp(100.0 - duplicate_rate * 10.0),
            "outlier_rate": _clamp(100.0 - outlier_rate * 8.0),
            "validation_success": components.validation_success,
            "source_agreement": components.source_agreement,
        }
        score = sum(self.weights[k] * sub[k] for k in self.weights)
        level = "EXCELLENT" if score >= 85 else "GOOD" if score >= 70 else "FAIR" if score >= 50 else "POOR"
        return TrustReport(
            trust_score=round(score, 1),
            level=level,
            components=components,
            weights=dict(self.weights),
            data_status=data_status,
            computed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )


def compute_trust_report_from_db() -> TrustReport:
    """Compute the trust report from the current SQLite state."""
    from ..config.db import get_db_connection
    conn = get_db_connection()

    total_routes = len(DGCA_TOP_20_ROUTES)
    total_windows = len(ADVANCE_PURCHASE_WINDOWS)
    total_cells = total_routes * total_windows

    # Freshness
    row = conn.execute("SELECT MAX(calculation_date) dt FROM national_indices").fetchone()
    age_days = None
    if row and row["dt"]:
        try:
            age_days = (datetime.date.today() - datetime.date.fromisoformat(row["dt"])).days
        except Exception:
            age_days = None

    # Completeness: route-window cells present on latest date
    latest = conn.execute("SELECT MAX(calculation_date) dt FROM route_indices").fetchone()
    present_cells = 0
    if latest and latest["dt"]:
        present_cells = conn.execute(
            "SELECT COUNT(*) c FROM route_indices WHERE calculation_date=?", (latest["dt"],)
        ).fetchone()["c"]

    routes_present = 0
    if latest and latest["dt"]:
        routes_present = conn.execute(
            "SELECT COUNT(DISTINCT route_code) c FROM route_indices WHERE calculation_date=?",
            (latest["dt"],)
        ).fetchone()["c"]

    # Sources
    source_rows = conn.execute("SELECT DISTINCT source_portal FROM raw_quotes").fetchall()
    sources_seen = len(source_rows)
    total_sources = len(EXPECTED_SOURCE_PORTALS)

    # Duplicate & outlier rates
    raw_cnt = conn.execute("SELECT COUNT(*) c FROM raw_quotes").fetchone()["c"]
    outlier_cnt = conn.execute("SELECT COUNT(*) c FROM cleaned_quotes WHERE outlier_flag=1").fetchone()["c"]
    # Duplicates estimated as raw minus kept unique quote ids
    kept = conn.execute("SELECT COUNT(DISTINCT quote_id) c FROM raw_quotes").fetchone()["c"]
    duplicate_rate = ((raw_cnt - kept) / max(1, raw_cnt)) * 100.0
    outlier_rate = (outlier_cnt / max(1, raw_cnt)) * 100.0

    # Validation success (from latest backtest)
    validation_score = 0.0
    bt = conn.execute("SELECT pearson_r, mape FROM backtest_metrics ORDER BY id DESC LIMIT 1").fetchone()
    if bt:
        validation_score = 100.0 if (bt["pearson_r"] >= 0.80 and bt["mape"] <= 4.5) else 40.0

    # Source agreement: average consensus score across latest route-window cells
    source_agreement = _compute_avg_consensus(conn)

    return DataTrustCalculator().compute(
        age_days=age_days, present_cells=present_cells, total_cells=total_cells,
        routes_present=routes_present, total_routes=total_routes,
        sources_seen=sources_seen, total_sources=total_sources,
        duplicate_rate=duplicate_rate, outlier_rate=outlier_rate,
        validation_score=validation_score, source_agreement=source_agreement,
        data_status="SIMULATED",
    )


def _compute_avg_consensus(conn) -> float:
    """Average source consensus across cleaned quotes (median/spread based)."""
    rows = conn.execute("""
        SELECT final_total_fare FROM cleaned_quotes
        WHERE outlier_flag=0 AND final_total_fare > 0
        LIMIT 2000
    """).fetchall()
    fares = [r["final_total_fare"] for r in rows]
    if not fares:
        return 50.0
    import numpy as np
    arr = np.array(fares, dtype=float)
    median = float(np.median(arr))
    if median <= 0:
        return 50.0
    cv = float(np.std(arr) / median)
    # Consensus inversely related to coefficient of variation
    return _clamp((1.0 - min(cv, 0.5)) * 100.0)
