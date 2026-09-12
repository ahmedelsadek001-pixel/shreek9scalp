import pytest

from core.live_authorization import evaluate_live_authorization, require_live_authorization


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


def test_complete_evidence_authorizes():
    result = evaluate_live_authorization(full_evidence())
    assert result.authorized is True
    assert result.missing == ()


def test_missing_evidence_blocks():
    evidence = full_evidence()
    evidence["broker_validation"] = False
    result = evaluate_live_authorization(evidence)
    assert result.authorized is False
    assert "broker_validation" in result.missing


def test_non_boolean_evidence_blocks():
    evidence = full_evidence()
    evidence["operator_approval"] = 1
    with pytest.raises(RuntimeError):
        require_live_authorization(evidence)
