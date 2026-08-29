"""Tests for source consensus and disagreement detection."""
from vayusutra_apix.analytics.consensus import ConsensusEngine


def _obs(values, sources=None):
    src = sources or [f"S{i}" for i in range(len(values))]
    return [{"source": src[i], "fare": v} for i, v in enumerate(values)]


def test_tight_cluster_is_normal():
    cc = ConsensusEngine().classify(_obs([5800, 5820, 5810, 5830]))
    assert cc.level == "NORMAL"
    assert cc.score > 80


def test_wide_spread_is_high_disagreement():
    cc = ConsensusEngine().classify(_obs([3000, 5800, 5900, 5850]))
    assert cc.level in ("WARNING", "HIGH DISAGREEMENT")


def test_outlier_source_flagged():
    cc = ConsensusEngine().classify(_obs([5800, 5820, 5810, 12000]))
    flagged = [s for s in cc.sources if s.flagged]
    assert len(flagged) == 1
    assert flagged[0].source_portal == "S3"


def test_empty_returns_no_data():
    cc = ConsensusEngine().classify([])
    assert cc.level == "NO DATA"


def test_cv_and_median_reported():
    cc = ConsensusEngine().classify(_obs([1000, 1000, 1000]))
    assert cc.median == 1000.0
    assert cc.cv == 0.0
