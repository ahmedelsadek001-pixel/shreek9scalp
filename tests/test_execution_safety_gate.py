import pytest

from execution.safety_gate import (
    ExecutionSafetyEvidence,
    evaluate_execution_safety,
    require_execution_safety,
)


def _complete() -> ExecutionSafetyEvidence:
    return ExecutionSafetyEvidence(True, True, True, True, True, True, True)


def test_complete_v53_safety_evidence_passes_without_live_authority():
    decision = evaluate_execution_safety(_complete())
    assert decision.ready is True
    assert decision.failures == ()


@pytest.mark.parametrize(
    "field",
    [
        "quote_safety_validated",
        "idempotency_validated",
        "outcome_classification_validated",
        "reconciliation_validated",
        "recovery_validated",
        "journal_integrity_validated",
        "live_execution_disabled",
    ],
)
def test_each_missing_v53_control_blocks(field):
    values = _complete().__dict__
    values[field] = False
    decision = evaluate_execution_safety(ExecutionSafetyEvidence(**values))
    assert decision.ready is False
    assert decision.failures
    if field == "live_execution_disabled":
        assert "live execution" in decision.failures[0]


def test_non_boolean_evidence_fails_closed():
    values = _complete().__dict__
    values["recovery_validated"] = 1
    decision = evaluate_execution_safety(ExecutionSafetyEvidence(**values))
    assert decision.ready is False
    with pytest.raises(RuntimeError, match="V5.3 execution-safety gate blocked"):
        require_execution_safety(ExecutionSafetyEvidence(**values))


def test_raw_mapping_is_not_accepted():
    with pytest.raises(TypeError):
        evaluate_execution_safety({"live_execution_disabled": True})
