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


def test_provenance_is_bound_to_evidence_hash():
    evidence = ResearchEvidence.create(
        "gold-2026",
        "V5.2",
        120,
        {"expectancy": 1.2, "win_rate": 57.5},
        data={"bars": 120, "symbol": "XAUUSD"},
        config={"risk": 0.01, "timeframe": "M5"},
        code_revision="abc123",
    )
    assert evidence.provenance is not None
    assert verify_evidence(evidence) is True


def test_partial_provenance_is_rejected():
    try:
        ResearchEvidence.create(
            "gold-2026", "V5.2", 120, {"expectancy": 1.2}, data={"bars": 120}
        )
    except ValueError as exc:
        assert "supplied together" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_provenance_tampering_fails_verification():
    evidence = ResearchEvidence.create(
        "gold-2026",
        "V5.2",
        120,
        {"expectancy": 1.2},
        data={"bars": 120},
        config={"risk": 0.01},
        code_revision="abc123",
    )
    object.__setattr__(evidence.provenance, "code_revision", "tampered")
    assert verify_evidence(evidence) is False
