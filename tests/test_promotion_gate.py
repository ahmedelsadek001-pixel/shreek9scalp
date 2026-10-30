import pytest

from core.promotion_gate import evaluate_v53_promotion
from execution.safety_gate import ExecutionSafetyEvidence
from research.research_release_gate import ResearchReleaseDecision


def _execution() -> ExecutionSafetyEvidence:
    return ExecutionSafetyEvidence(True, True, True, True, True, True, True)


def test_v53_promotion_rejects_manual_success_without_artifact():
    decision = evaluate_v53_promotion(ResearchReleaseDecision(True, ()), _execution())
    assert decision.ready is False
    assert decision.failures == ("V5.2 promotion requires a validated research release package",)


def test_failed_v52_research_blocks_v53_even_when_safety_passes():
    decision = evaluate_v53_promotion(
        ResearchReleaseDecision(False, ("robustness is not validated",)),
        _execution(),
    )
    assert decision.ready is False
    assert decision.failures == ("V5.2 promotion blocked: robustness is not validated",)


def test_missing_execution_safety_blocks_v53():
    execution = ExecutionSafetyEvidence(True, True, True, True, True, True, False)
    decision = evaluate_v53_promotion(ResearchReleaseDecision(True, ()), execution)
    assert decision.ready is False
    assert "V5.2 promotion requires a validated research release package" in decision.failures
    assert "V5.3 execution safety blocked: live execution is not explicitly disabled" in decision.failures


def test_inconsistent_manual_decision_blocks_promotion():
    decision = evaluate_v53_promotion(
        ResearchReleaseDecision(True, ("robustness is not validated",)), _execution()
    )
    assert decision.ready is False
    assert "V5.2 research decision is inconsistent" in decision.failures


@pytest.mark.parametrize("value", [None, {"ready": True}])
def test_promotion_rejects_malformed_research_decision(value):
    with pytest.raises(TypeError):
        evaluate_v53_promotion(value, _execution())
