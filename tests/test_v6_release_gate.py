import pytest

from core.v6_release_gate import evaluate_v6_release, require_v6_release


def full_evidence():
    return {
        "ci_green": True,
        "tests_green": True,
        "data_integrity_validated": True,
        "walk_forward_passed": True,
        "robustness_passed": True,
        "paper_trading_validated": True,
        "security_reviewed": True,
        "execution_reconciled": True,
        "shadow_validated": True,
        "recovery_validated": True,
        "broker_validation": True,
        "operator_approval": True,
    }


def test_v6_release_ready_with_complete_evidence():
    decision = evaluate_v6_release(full_evidence())
    assert decision.release_ready is True
    assert decision.failures == ()


def test_v6_release_fails_closed():
    evidence = full_evidence()
    evidence["robustness_passed"] = False
    decision = evaluate_v6_release(evidence)
    assert decision.release_ready is False
    assert any("robustness_passed" in item for item in decision.failures)
    with pytest.raises(RuntimeError):
        require_v6_release(evidence)
