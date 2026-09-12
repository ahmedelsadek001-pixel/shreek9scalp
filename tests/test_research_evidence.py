from research.research_evidence import ResearchEvidence, verify_evidence


def test_evidence_is_reproducible_and_verifiable():
    evidence = ResearchEvidence.create("gold-2026", "V5.2", 120, {"expectancy": 1.2, "win_rate": 57.5})
    assert verify_evidence(evidence) is True
    assert evidence.evidence_hash == ResearchEvidence.create(
        "gold-2026", "V5.2", 120, {"win_rate": 57.5, "expectancy": 1.2}
    ).evidence_hash


def test_invalid_evidence_rejected():
    try:
        ResearchEvidence.create("", "V5.2", 10, {})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
