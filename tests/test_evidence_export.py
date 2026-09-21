from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.block_bootstrap import BlockBootstrapSummary
from core.research_certification import ResearchCertification
from core.statistical_evidence import MeanConfidenceInterval
from research.dataset_provenance import DatasetProvenance
from research.evidence_export import (
    build_evidence_export,
    fingerprint_evidence_export,
    serialize_evidence_export,
)
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport


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


def test_export_is_deterministic():
    result = _result(EvidenceGatePolicy(min_expectancy=1.0))
    first = serialize_evidence_export(result, _provenance())
    second = serialize_evidence_export(result, _provenance())
    assert first == second
    assert fingerprint_evidence_export(result, _provenance()) == fingerprint_evidence_export(result, _provenance())


def test_export_contains_dataset_identity_evidence_and_exact_policy():
    policy = EvidenceGatePolicy(min_oos_trades=30, min_expectancy=1.0)
    payload = build_evidence_export(_result(policy), _provenance())
    assert payload["schema_version"] == "3"
    assert payload["dataset"]["sha256"] == "a" * 64
    assert "oos_expectancy" in payload["evidence"]
    assert payload["gate"]["passed"] is True
    assert payload["gate_policy"]["min_expectancy"] == 1.0


def test_export_rejects_invalid_policy():
    invalid = EvidenceGatePolicy(min_oos_trades=0)
    with pytest.raises(ValueError, match="min_oos_trades"):
        build_evidence_export(_result(invalid), _provenance())


def _certified_result():
    base = _result()
    interval = MeanConfidenceInterval(30, 3.0, 0.5, 0.95, 2.0, 4.0)
    bootstrap = BlockBootstrapSummary(30, 2, 100, 0.95, 3.0, 3.0, 2.0, 4.0, 0.0)
    certification = ResearchCertification(True, (), 30, 4, 75.0)
    return replace(
        base,
        interval=interval,
        bootstrap=bootstrap,
        certification=certification,
    )


def test_export_binds_complete_statistical_certification():
    payload = build_evidence_export(_certified_result(), _provenance())
    statistical = payload["statistical_evidence"]
    assert statistical["confidence_interval"]["samples"] == 30
    assert statistical["block_bootstrap"]["samples"] == 30
    assert statistical["certification"]["passed"] is True
    assert statistical["certification_policy"]["min_oos_trades"] == 30


def test_export_rejects_partial_statistical_certification():
    result = replace(
        _certified_result(),
        certification=None,
    )
    with pytest.raises(ValueError, match="statistical certification evidence must be complete"):
        build_evidence_export(result, _provenance())


def test_statistical_evidence_changes_export_fingerprint():
    original = _certified_result()
    tampered = replace(
        original,
        certification=replace(original.certification, passed=False, failures=("tampered",)),
    )
    assert fingerprint_evidence_export(original, _provenance()) != fingerprint_evidence_export(
        tampered, _provenance()
    )
