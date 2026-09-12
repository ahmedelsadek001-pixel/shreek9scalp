import pytest

from core.v6_release_gate import evaluate_v6_release, require_v6_release


def full_evidence():
    return {
        "ci_green": True,
        "historical_validation": True,
        "walk_forward": True,
        "robustness": True,
        "paper_trading": True,
        "security_review": True,
        "shadow_validation": True,
        "recovery_validation": True,
        "broker_validation": True,
        "operator_approval": True,
    }


def test_v6_release_ready_with_complete_evidence():
    decision = evaluate_v6_release(full_evidence())
    assert decision.release_ready is True
    assert decision.failures == ()


def test_v6_release_fails_closed():
    evidence = full_evidence()
    evidence["robustness"] = False
    decision = evaluate_v6_release(evidence)
    assert decision.release_ready is False
    assert any("robustness" in item for item in decision.failures)
    with pytest.raises(RuntimeError):
        require_v6_release(evidence)
