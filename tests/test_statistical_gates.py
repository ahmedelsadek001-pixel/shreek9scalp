import pytest

from research.bootstrap_validation import bootstrap_expectancy
from research.edge_matrix import EdgeCell
from research.statistical_gates import StatisticalGatePolicy, evaluate_statistical_gate


def cell(trades=30, expectancy=1.0, win_rate=55.0):
    return EdgeCell("FVG", "TREND", trades, 0, 0, expectancy * trades, expectancy, win_rate, trades)


def test_strong_statistical_evidence_passes():
    pnl = [1.0] * 30 + [2.0] * 10
    bootstrap = bootstrap_expectancy(pnl, simulations=500, seed=7)
    result = evaluate_statistical_gate(cell(40, 1.25, 65.0), bootstrap)
    assert result.passed is True
    assert result.reasons == ()


def test_sparse_sample_blocks():
    pnl = [1.0] * 20 + [-1.0] * 10
    bootstrap = bootstrap_expectancy(pnl, simulations=500, seed=3)
    result = evaluate_statistical_gate(cell(20, 0.5, 60.0), bootstrap)
    assert result.passed is False
    assert "sample count below minimum" in result.reasons


def test_mismatched_sample_count_blocks():
    bootstrap = bootstrap_expectancy([1.0, 1.0, 1.0, 1.0], simulations=500, seed=1)
    result = evaluate_statistical_gate(cell(30, 1.0, 60.0), bootstrap)
    assert result.passed is False
    assert "bootstrap sample count does not match edge cell" in result.reasons


def test_policy_validation():
    with pytest.raises(ValueError):
        evaluate_statistical_gate(cell(), bootstrap_expectancy([1.0, 2.0], simulations=500), StatisticalGatePolicy(min_samples=0))
