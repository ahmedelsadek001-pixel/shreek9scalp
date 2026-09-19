"""Validation tests for immutable research evidence records."""
import math

import pytest

from core.research_evidence import ResearchEvidence, verify_evidence


def test_evidence_freezes_metrics_and_verifies_hash():
    source = {"return": 1.25}
    evidence = ResearchEvidence.create("dataset-A", "strategy-1", 12, source)
    source["return"] = 99.0

    assert evidence.metrics["return"] == 1.25
    assert verify_evidence(evidence)
    with pytest.raises(TypeError):
        evidence.metrics["return"] = 2.0


@pytest.mark.parametrize("value", [True, False, "1", None, float("inf"), float("nan"), -float("inf"), 10**10000])
def test_rejects_invalid_metric_values(value):
    with pytest.raises(ValueError):
        ResearchEvidence.create("dataset-A", "strategy-1", 1, {"metric": value})


@pytest.mark.parametrize("sample_size", [True, False, 1.5, "2", 0, -1])
def test_sample_size_must_be_positive_integer(sample_size):
    with pytest.raises(ValueError):
        ResearchEvidence.create("dataset-A", "strategy-1", sample_size, {})


@pytest.mark.parametrize("dataset_id,strategy", [(None, "v1"), ("", "v1"), ("data", None), ("data", " ")])
def test_identifiers_are_required_strings(dataset_id, strategy):
    with pytest.raises(ValueError):
        ResearchEvidence.create(dataset_id, strategy, 1, {})


@pytest.mark.parametrize("metrics", [None, [], {"": 1.0}, {1: 1.0}])
def test_rejects_invalid_metric_mapping_or_name(metrics):
    with pytest.raises(ValueError):
        ResearchEvidence.create("dataset-A", "strategy-1", 1, metrics)


def test_verify_evidence_fails_closed_for_wrong_type_and_tampered_record():
    evidence = ResearchEvidence.create("dataset-A", "strategy-1", 1, {"score": 2.0})
    assert not verify_evidence(object())

    tampered = ResearchEvidence(
        evidence.dataset_id,
        evidence.strategy_version,
        evidence.sample_size,
        {"score": math.inf},
        evidence.evidence_hash,
    )
    assert not verify_evidence(tampered)
