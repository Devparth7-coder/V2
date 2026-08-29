"""
VayuSutra APIx - Source Consensus & Disagreement Detection
Compares fares across sources (airlines / OTAs) for a route and computes median, spread,
coefficient of variation, and a consensus score. Flags substantially different sources as
NORMAL / WARNING / HIGH DISAGREEMENT without automatically deleting them.
"""
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import numpy as np


@dataclass
class SourceConsensus:
    source_portal: str
    median_fare: Optional[float]
    deviation_from_median_pct: float = 0.0
    flagged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_portal": self.source_portal,
            "median_fare": self.median_fare,
            "deviation_from_median_pct": round(self.deviation_from_median_pct, 2),
            "flagged": self.flagged,
        }


@dataclass
class ConsensusClassification:
    level: str
    score: float          # 0-100 consensus score
    spread: float
    cv: float
    median: float
    sources: List[SourceConsensus]
    route_code: Optional[str] = None
    advance_window: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "score": round(self.score, 1),
            "spread": round(self.spread, 2),
            "coefficient_of_variation": round(self.cv, 4),
            "median": round(self.median, 2),
            "route_code": self.route_code,
            "advance_window": self.advance_window,
            "sources": [s.to_dict() for s in self.sources],
            "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


class ConsensusEngine:
    """Computes consensus for a group of (source, fare) observations."""

    NORMAL_CV = 0.06      # <=6% spread considered normal
    WARNING_CV = 0.15     # >6% but <=15% warning
    FLAG_DEVIATION = 0.15 # flag a source deviating >15% from median

    def classify(self, observations: List[Dict[str, Any]]) -> ConsensusClassification:
        if not observations:
            return ConsensusClassification("NO DATA", 0.0, 0.0, 0.0, 0.0, [])
        fares = np.array([o["fare"] for o in observations], dtype=float)
        fares = fares[fares > 0]
        if len(fares) == 0:
            return ConsensusClassification("NO DATA", 0.0, 0.0, 0.0, 0.0, [])
        median = float(np.median(fares))
        std = float(np.std(fares))
        spread = std * 2.0
        cv = std / median if median > 0 else 0.0
        if cv <= self.NORMAL_CV:
            level = "NORMAL"
            score = 100.0 - (cv / self.NORMAL_CV) * 20.0
        elif cv <= self.WARNING_CV:
            level = "WARNING"
            score = 80.0 - ((cv - self.NORMAL_CV) / (self.WARNING_CV - self.NORMAL_CV)) * 30.0
        else:
            level = "HIGH DISAGREEMENT"
            score = max(0.0, 50.0 - (cv - self.WARNING_CV) * 100.0)

        source_list: List[SourceConsensus] = []
        for o in observations:
            dev = ((o["fare"] - median) / median * 100.0) if median > 0 else 0.0
            flagged = abs(dev) > (self.FLAG_DEVIATION * 100.0)
            source_list.append(SourceConsensus(
                source_portal=o.get("source", "UNKNOWN"),
                median_fare=float(o["fare"]),
                deviation_from_median_pct=float(dev),
                flagged=flagged,
            ))

        return ConsensusClassification(
            level=level, score=max(0.0, min(100.0, score)),
            spread=float(spread), cv=float(cv), median=float(median),
            sources=source_list,
        )


def compute_source_consensus_from_db(route_code: Optional[str] = None,
                                     advance_window: Optional[str] = None) -> List[ConsensusClassification]:
    """
    Compute per-route-window consensus from cleaned quotes. Returns one classification
    per (route_code, advance_window) group, optionally filtered.
    """
    from ..config.db import get_db_connection
    conn = get_db_connection()
    q = """
        SELECT c.route_code, c.advance_window, r.source_portal, c.final_total_fare AS fare
        FROM cleaned_quotes c
        LEFT JOIN raw_quotes r ON c.raw_quote_id = r.quote_id
        WHERE c.outlier_flag=0 AND c.final_total_fare > 0
    """
    params: list = []
    if route_code:
        q += " AND c.route_code=?"
        params.append(route_code.upper())
    if advance_window:
        q += " AND c.advance_window=?"
        params.append(advance_window.upper())
    q += " ORDER BY c.route_code, c.advance_window"
    rows = conn.execute(q, params).fetchall()

    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["route_code"], r["advance_window"]), []).append({
            "source": r["source_portal"], "fare": r["fare"],
        })

    engine = ConsensusEngine()
    results: List[ConsensusClassification] = []
    for key in sorted(groups.keys()):
        cc = engine.classify(groups[key])
        cc.route_code = key[0]
        cc.advance_window = key[1]
        results.append(cc)
    return results
