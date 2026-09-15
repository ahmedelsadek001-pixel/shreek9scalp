from datetime import datetime, timezone

from research.dataset_provenance import DatasetProvenance
from research.evidence_export import (
    build_evidence_export,
    fingerprint_evidence_export,
    serialize_evidence_export,
)
from research.evidence_gate import EvidenceGateResult
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport


def _provenance():
    return DatasetProvenance(
        "1", "a" * 64, 2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )


def _result():
    report = OOSEvidenceReport(
        30, 100.0, 3.333333, 75.0, 3, 4, 0.0,
        10100.0, 10000.0, 50.0, 100.0, 1000,
    )
    return EvidencePipelineResult(object(), object(), report, EvidenceGateResult(True, ()))


def test_export_is_deterministic():
    result = _result()
    first = serialize_evidence_export(result, _provenance())
    second = serialize_evidence_export(result, _provenance())
    assert first == second
    assert fingerprint_evidence_export(result, _provenance()) == fingerprint_evidence_export(result, _provenance())


def test_export_contains_dataset_identity_and_evidence():
    payload = build_evidence_export(_result(), _provenance())
    assert payload["schema_version"] == "1"
    assert payload["dataset"]["sha256"] == "a" * 64
    assert "oos_expectancy" in payload["evidence"]
    assert payload["gate"]["passed"] is True
