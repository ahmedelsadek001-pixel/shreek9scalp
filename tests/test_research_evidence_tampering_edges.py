import pytest

from research.research_evidence import ResearchEvidence, verify_evidence


@pytest.mark.parametrize(
    "metrics",
    [
        {"expectancy": True},
        {"expectancy": "1.25"},
        {"expectancy": float("inf")},
        {"expectancy": 10**10000},
        {" expectancy ": 1.0, "expectancy": 2.0},
    ],
    ids=["boolean", "numeric-string", "infinity", "huge-integer", "normalized-name-collision"],
)
def test_verify_evidence_fails_closed_for_tampered_metrics(metrics):
    evidence = ResearchEvidence.create("gold-2026", "V5.2", 120, {"expectancy": 1.0})
    object.__setattr__(evidence, "metrics", metrics)
    assert verify_evidence(evidence) is False


def test_verify_evidence_rejects_tampered_invalid_sample_count():
    evidence = ResearchEvidence.create("gold-2026", "V5.2", 120, {"expectancy": 1.0})
    object.__setattr__(evidence, "samples", True)
    assert verify_evidence(evidence) is False


def test_verify_evidence_rejects_tampered_blank_identity_fields():
    evidence = ResearchEvidence.create("gold-2026", "V5.2", 120, {"expectancy": 1.0})
    object.__setattr__(evidence, "dataset_id", "   ")
    assert verify_evidence(evidence) is False
