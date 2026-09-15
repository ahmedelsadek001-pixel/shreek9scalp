import pytest

from research.evidence_gate import EvidenceGatePolicy, evaluate_oos_evidence
from research.evidence_report import OOSEvidenceReport


def _report(**overrides):
    values = dict(
        oos_trade_count=40,
        oos_net_pnl=120.0,
        oos_expectancy=3.0,
        oos_stability_pct=75.0,
        positive_oos_windows=3,
        oos_window_count=4,
        ruin_rate_pct=0.0,
        median_ending_equity=10120.0,
        worst_ending_equity=10020.0,
        median_max_drawdown=50.0,
        worst_max_drawdown=100.0,
        simulations=100,
    )
    values.update(overrides)
    return OOSEvidenceReport(**values)


def test_evidence_gate_passes_clean_oos_evidence():
    result = evaluate_oos_evidence(_report())
    assert result.passed
    assert result.failures == ()


def test_evidence_gate_fails_each_material_threshold():
    policy = EvidenceGatePolicy(
        min_oos_trades=50,
        min_expectancy=4.0,
        min_oos_stability_pct=80.0,
        max_ruin_rate_pct=0.0,
        max_worst_drawdown=90.0,
    )
    result = evaluate_oos_evidence(_report(ruin_rate_pct=1.0), policy)
    assert not result.passed
    assert len(result.failures) == 5


def test_evidence_gate_rejects_unvalidated_report():
    with pytest.raises(ValueError, match="report requires"):
        evaluate_oos_evidence(_report(oos_trade_count=0))


def test_policy_rejects_invalid_trade_threshold():
    with pytest.raises(ValueError, match="min_oos_trades"):
        EvidenceGatePolicy(min_oos_trades=0).validate()


def test_policy_rejects_boolean_numeric_thresholds():
    with pytest.raises(ValueError, match="must not be bool"):
        EvidenceGatePolicy(min_expectancy=True).validate()


def test_policy_rejects_non_finite_expectancy():
    with pytest.raises(ValueError, match="min_expectancy"):
        EvidenceGatePolicy(min_expectancy=float("inf")).validate()


def test_policy_rejects_invalid_stability_range():
    with pytest.raises(ValueError, match="stability"):
        EvidenceGatePolicy(min_oos_stability_pct=101.0).validate()


def test_policy_rejects_negative_ruin_limit():
    with pytest.raises(ValueError, match="max_ruin_rate_pct"):
        EvidenceGatePolicy(max_ruin_rate_pct=-0.1).validate()


def test_policy_allows_unbounded_drawdown_explicitly():
    EvidenceGatePolicy(max_worst_drawdown=float("inf")).validate()


def test_policy_rejects_negative_drawdown_limit():
    with pytest.raises(ValueError, match="drawdown"):
        EvidenceGatePolicy(max_worst_drawdown=-1.0).validate()
