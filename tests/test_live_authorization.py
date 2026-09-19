import pytest

from core.live_authorization import evaluate_live_authorization, require_live_authorization


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


def test_missing_key_blocks():
    evidence = full_evidence()
    del evidence["execution_reconciled"]
    result = evaluate_live_authorization(evidence)
    assert result.authorized is False
    assert result.missing == ("execution_reconciled",)


def test_non_mapping_input_is_rejected():
    with pytest.raises(TypeError):
        evaluate_live_authorization(None)


def test_every_required_evidence_item_is_mandatory():
    for key in full_evidence():
        evidence = full_evidence()
        del evidence[key]

        result = evaluate_live_authorization(evidence)
        assert result.authorized is False, f"authorization unexpectedly passed without {key}"
        assert key in result.missing
        with pytest.raises(RuntimeError):
            require_live_authorization(evidence)
