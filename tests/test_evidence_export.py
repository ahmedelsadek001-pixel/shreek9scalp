from datetime import datetime, timezone

from research.dataset_provenance import DatasetProvenance
from research.evidence_export import (
    build_evidence_export,
    fingerprint_evidence_export,
    serialize_evidence_export,
)


def _provenance():
    return DatasetProvenance(
        "1",
        "a" * 64,
        2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )


def test_export_is_deterministic(fake_evidence_pipeline_result):
    result = fake_evidence_pipeline_result
    first = serialize_evidence_export(result, _provenance())
    second = serialize_evidence_export(result, _provenance())
    assert first == second
    assert fingerprint_evidence_export(result, _provenance()) == fingerprint_evidence_export(result, _provenance())


def test_export_contains_dataset_identity_and_evidence(fake_evidence_pipeline_result):
    payload = build_evidence_export(fake_evidence_pipeline_result, _provenance())
    assert payload["schema_version"] == "1"
    assert payload["dataset"]["sha256"] == "a" * 64
    assert "oos_expectancy" in payload["evidence"]
    assert "passed" in payload["gate"]
