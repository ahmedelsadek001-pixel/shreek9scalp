import pytest

from research.research_release_gate import (
    ResearchReleaseEvidence,
    evaluate_research_release,
)


def complete():
    return ResearchReleaseEvidence(True, True, True, True, True, True, True, True, True, True, True, True)


def test_complete_research_evidence_is_ready():
    result = evaluate_research_release(complete())
    assert result.ready is True
    assert result.failures == ()


def test_missing_research_evidence_blocks():
    evidence = ResearchReleaseEvidence(True, True, True, True, False, True, True, True, True, True, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "purged walk-forward validation is not validated" in result.failures


def test_missing_bootstrap_evidence_blocks():
    evidence = ResearchReleaseEvidence(True, True, True, True, True, True, False, True, True, True, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "bootstrap expectancy validation is not validated" in result.failures


def test_non_boolean_research_evidence_fails_closed():
    with pytest.raises(TypeError):
        evaluate_research_release("bad")


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("dataset_provenance_validated", "dataset provenance is not validated"),
        ("reproducible_artifact_validated", "reproducible research artifact is not validated"),
        ("strategy_version_bound", "research artifact is not bound to strategy version"),
    ],
)
def test_release_blocks_missing_reproducibility_evidence(field, message):
    evidence = complete()
    values = evidence.__dict__.copy()
    values[field] = False
    result = evaluate_research_release(ResearchReleaseEvidence(**values))
    assert result.ready is False
    assert message in result.failures


def test_legacy_release_evidence_shape_fails_closed_on_new_artifact_gates():
    evidence = ResearchReleaseEvidence(True, True, True, True, True, True, True, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "dataset provenance is not validated" in result.failures
    assert "reproducible research artifact is not validated" in result.failures
    assert "research artifact is not bound to strategy version" in result.failures
