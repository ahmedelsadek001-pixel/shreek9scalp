import pytest

from core.release_gate import (
    ReleaseEvidence,
    evaluate_release,
    require_release_ready,
)


def _evidence(**overrides):
    values = dict(
        ci_green=True,
        tests_green=True,
        data_integrity_validated=True,
        walk_forward_passed=True,
        robustness_passed=True,
        paper_trading_validated=True,
        security_reviewed=True,
        execution_reconciled=True,
    )
    values.update(overrides)
    return ReleaseEvidence(**values)


def test_release_gate_requires_every_control():
    decision = evaluate_release(_evidence())
    assert decision.ready
    assert decision.failures == ()


def test_release_gate_blocks_missing_control():
    decision = evaluate_release(_evidence(robustness_passed=False))
    assert not decision.ready
    assert "robustness validation has not passed" in decision.failures


def test_release_gate_rejects_non_boolean_evidence():
    decision = evaluate_release(_evidence(ci_green=1))
    assert not decision.ready
    assert "CI is not green" in decision.failures


def test_require_release_ready_fails_closed():
    with pytest.raises(RuntimeError, match="release gate blocked"):
        require_release_ready(_evidence(security_reviewed=False))
