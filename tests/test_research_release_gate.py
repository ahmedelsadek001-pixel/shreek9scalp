import pytest

from research.research_release_gate import (
    ResearchReleaseEvidence,
    evaluate_research_release,
)


def complete():
    return ResearchReleaseEvidence(True, True, True, True, True, True, True, True, True)


def test_complete_research_evidence_is_ready():
    result = evaluate_research_release(complete())
    assert result.ready is True
    assert result.failures == ()


def test_missing_research_evidence_blocks():
    evidence = ResearchReleaseEvidence(True, True, True, True, False, True, True, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "purged walk-forward validation is not validated" in result.failures


def test_missing_bootstrap_evidence_blocks():
    evidence = ResearchReleaseEvidence(True, True, True, True, True, True, False, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "bootstrap expectancy validation is not validated" in result.failures


def test_non_boolean_research_evidence_fails_closed():
    with pytest.raises(TypeError):
        evaluate_research_release("bad")
