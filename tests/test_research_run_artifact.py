from datetime import datetime, timezone

import pytest

from research.dataset_provenance import DatasetProvenance
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport
from research.research_run_artifact import (
    ResearchRunArtifact,
    build_research_run_artifact,
    fingerprint_research_run_artifact,
    serialize_research_run_artifact,
)


def _provenance():
    return DatasetProvenance(
        "1", "a" * 64, 2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )


def _result(policy=None):
    report = OOSEvidenceReport(
        30, 100.0, 3.333333, 75.0, 3, 4, 0.0,
        10100.0, 10000.0, 50.0, 100.0, 1000,
    )
    policy = policy or EvidenceGatePolicy()
    return EvidencePipelineResult(
        object(), object(), report, EvidenceGateResult(True, ()), policy
    )


def test_artifact_is_deterministic_and_fingerprinted():
    artifact = build_research_run_artifact(
        _result(), _provenance(), metadata={"run": "1", "source": "local"}
    )
    assert serialize_research_run_artifact(artifact) == serialize_research_run_artifact(artifact)
    assert fingerprint_research_run_artifact(artifact) == fingerprint_research_run_artifact(artifact)
    artifact.validate()


def test_artifact_binds_exact_evidence_export():
    artifact = build_research_run_artifact(
        _result(EvidenceGatePolicy(min_expectancy=1.0)), _provenance()
    )
    assert artifact.evidence_export_sha256 == __import__("hashlib").sha256(
        artifact.evidence_export.encode("utf-8")
    ).hexdigest()
    assert '"gate_policy"' in artifact.evidence_export


def test_artifact_changes_when_metadata_changes():
    first = build_research_run_artifact(_result(), _provenance(), metadata={"run": "1"})
    second = build_research_run_artifact(_result(), _provenance(), metadata={"run": "2"})
    assert fingerprint_research_run_artifact(first) != fingerprint_research_run_artifact(second)


def test_artifact_rejects_tampered_export():
    artifact = build_research_run_artifact(_result(), _provenance())
    tampered = ResearchRunArtifact(
        artifact.schema_version,
        artifact.dataset,
        artifact.evidence_export_sha256,
        artifact.evidence_export + "x",
        artifact.metadata,
    )
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        tampered.validate()
