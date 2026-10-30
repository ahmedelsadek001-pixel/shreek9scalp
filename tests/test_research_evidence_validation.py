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


@pytest.mark.parametrize(
    "value",
    [True, False, "1", None, float("inf"), float("nan"), -float("inf"), 10**10000],
    ids=["true", "false", "string", "none", "positive-inf", "nan", "negative-inf", "huge-int"],
)
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
        evidence.version,
        evidence.samples,
        {"score": math.inf},
        evidence.evidence_hash,
    )
    assert not verify_evidence(tampered)

    boolean_tampered = ResearchEvidence(
        evidence.dataset_id,
        evidence.version,
        evidence.samples,
        {"score": True},
        evidence.evidence_hash,
    )
    assert not verify_evidence(boolean_tampered)

    string_tampered = ResearchEvidence(
        evidence.dataset_id,
        evidence.version,
        evidence.samples,
        {"score": "2.0"},
        evidence.evidence_hash,
    )
    assert not verify_evidence(string_tampered)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset_id", ""),
        ("dataset_id", None),
        ("version", " "),
        ("version", None),
        ("samples", True),
        ("samples", 0),
        ("samples", 1.5),
        ("evidence_hash", ""),
        ("metrics", {}),
        ("metrics", None),
    ],
    ids=["empty-dataset", "none-dataset", "blank-version", "none-version", "bool-samples", "zero-samples", "float-samples", "empty-hash", "empty-metrics", "none-metrics"],
)
def test_verify_rejects_invalid_metadata(field, value):
    evidence = ResearchEvidence.create("dataset-A", "strategy-1", 2, {"score": 1.0})
    altered = {
        "dataset_id": evidence.dataset_id,
        "version": evidence.version,
        "samples": evidence.samples,
        "metrics": evidence.metrics,
        "evidence_hash": evidence.evidence_hash,
        "provenance": evidence.provenance,
    }
    altered[field] = value
    tampered = ResearchEvidence(**altered)
    assert not verify_evidence(tampered)


def test_create_rejects_metric_names_colliding_after_whitespace_normalization():
    with pytest.raises(ValueError, match="unique after normalization"):
        ResearchEvidence.create("dataset-A", "strategy-1", 1, {"score": 1.0, " score ": 2.0})


def test_verify_rejects_metric_names_colliding_after_whitespace_normalization():
    evidence = ResearchEvidence.create("dataset-A", "strategy-1", 1, {"score": 1.0})
    tampered = ResearchEvidence(
        evidence.dataset_id,
        evidence.version,
        evidence.samples,
        {"score": 1.0, " score ": 2.0},
        evidence.evidence_hash,
    )
    assert not verify_evidence(tampered)


@pytest.mark.parametrize(
    "data,config,revision",
    [
        ({"bars": 1}, None, "abc123"),
        (None, {"risk": 0.01}, "abc123"),
        ({"bars": 1}, {"risk": 0.01}, None),
        ({"bars": 1}, {"risk": 0.01}, " "),
    ],
    ids=["missing-config", "missing-data", "missing-revision", "blank-revision"],
)
def test_create_requires_complete_valid_provenance(data, config, revision):
    with pytest.raises(ValueError):
        ResearchEvidence.create(
            "dataset-A",
            "strategy-1",
            1,
            {"score": 1.0},
            data=data,
            config=config,
            code_revision=revision,
        )


def test_evidence_with_complete_provenance_verifies():
    evidence = ResearchEvidence.create(
        "dataset-A",
        "strategy-1",
        3,
        {"score": 0.75},
        data={"closes": [2300.0, 2301.0, 2302.0]},
        config={"risk_fraction": 0.01},
        code_revision="abc123",
    )
    assert evidence.provenance is not None
    assert verify_evidence(evidence)
