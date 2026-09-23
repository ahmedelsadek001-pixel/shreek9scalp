from datetime import datetime, timezone

import pytest

from research.dataset_provenance import DatasetProvenance
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport
from research.research_run_artifact import build_research_run_artifact

from research.research_release_gate import (
    ResearchReleaseEvidence,
    ResearchReleasePackage,
    evaluate_research_release,
    evaluate_research_release_package,
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



def _release_artifact(strategy_id="breakout-retest", strategy_version="research-v1"):
    provenance = DatasetProvenance(
        "1",
        "a" * 64,
        2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    report = OOSEvidenceReport(
        30, 100.0, 3.333333, 75.0, 3, 4, 0.0,
        10100.0, 10000.0, 50.0, 100.0, 1000,
    )
    result = EvidencePipelineResult(
        object(),
        object(),
        report,
        EvidenceGateResult(True, ()),
        EvidenceGatePolicy(),
    )
    return build_research_run_artifact(
        result,
        provenance,
        metadata={
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
        },
    )


def test_release_package_accepts_exact_strategy_bound_artifact():
    package = ResearchReleasePackage(
        complete(),
        _release_artifact(),
        "breakout-retest",
        "research-v1",
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is True
    assert decision.failures == ()


@pytest.mark.parametrize(
    ("strategy_id", "strategy_version"),
    [
        ("wrong", "research-v1"),
        ("breakout-retest", "wrong"),
    ],
)
def test_release_package_blocks_strategy_identity_mismatch(strategy_id, strategy_version):
    package = ResearchReleasePackage(
        complete(),
        _release_artifact(),
        strategy_id,
        strategy_version,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert decision.failures == ("research artifact identity validation failed",)
