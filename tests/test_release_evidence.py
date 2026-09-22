from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.release_evidence import EvidenceRecord, ReleaseEvidenceBundle, evaluate_evidence_bundle
from core.release_gate import ReleaseEvidence


_COMMIT = "a" * 40


def _required() -> ReleaseEvidence:
    return ReleaseEvidence(True, True, True, True, True, True, True, True, True, True)


def _bundle() -> ReleaseEvidenceBundle:
    names = (
        "ci_green", "tests_green", "data_integrity_validated", "walk_forward_passed",
        "robustness_passed", "paper_trading_validated", "security_reviewed",
        "execution_reconciled", "shadow_validated", "recovery_validated",
    )
    records = tuple(
        EvidenceRecord(name, True, "validated-test", "run-001", datetime(2026, 9, 12, tzinfo=timezone.utc), _COMMIT)
        for name in names
    )
    return ReleaseEvidenceBundle.from_records(records)


def test_bundle_requires_nonempty_records():
    with pytest.raises(ValueError):
        ReleaseEvidenceBundle.from_records(())


def test_record_requires_provenance():
    with pytest.raises(ValueError):
        EvidenceRecord("ci_green", True, "", "run-1", datetime.now(timezone.utc), _COMMIT).validate()


def test_record_requires_valid_commit_sha():
    with pytest.raises(ValueError):
        EvidenceRecord("ci_green", True, "test", "run-1", datetime.now(timezone.utc), "not-a-sha").validate()


def test_unknown_evidence_name_is_rejected():
    with pytest.raises(ValueError):
        EvidenceRecord("invented_flag", True, "test", "run-1", datetime.now(timezone.utc), _COMMIT).validate()


def test_duplicate_evidence_name_is_rejected():
    record = EvidenceRecord("ci_green", True, "test", "run-1", datetime.now(timezone.utc), _COMMIT)
    with pytest.raises(ValueError):
        ReleaseEvidenceBundle.from_records((record, record))


def test_complete_provenance_bundle_can_pass_release_gate():
    decision = evaluate_evidence_bundle(_bundle(), _required())
    assert decision.ready
    assert not decision.failures


def test_missing_provenance_blocks_release_even_if_required_flag_is_true():
    records = tuple(_bundle().records[:-1])
    bundle = ReleaseEvidenceBundle.from_records(records)
    decision = evaluate_evidence_bundle(bundle, _required())
    assert not decision.ready
    assert "recovery_validated" in decision.failures[0]


def test_required_policy_blocks_failed_required_evidence():
    records = list(_bundle().records)
    records[0] = EvidenceRecord("ci_green", False, "validated-test", "run-001", datetime(2026, 9, 12, tzinfo=timezone.utc), _COMMIT)
    bundle = ReleaseEvidenceBundle.from_records(tuple(records))
    decision = evaluate_evidence_bundle(bundle, _required())
    assert not decision.ready
    assert decision.failures == ("required evidence failed: ci_green",)


def test_bundle_id_is_order_independent_for_same_records():
    first = _bundle()
    second = ReleaseEvidenceBundle.from_records(tuple(reversed(first.records)))
    assert first.bundle_id == second.bundle_id
    assert first.commit_sha == _COMMIT


def test_mixed_commit_evidence_is_rejected():
    records = list(_bundle().records)
    records[-1] = replace(records[-1], commit_sha="b" * 40)
    with pytest.raises(ValueError, match="same commit SHA"):
        ReleaseEvidenceBundle.from_records(tuple(records))


def test_tampered_bundle_id_is_rejected():
    tampered = replace(_bundle(), bundle_id="0" * 64)
    with pytest.raises(ValueError, match="bundle_id"):
        tampered.validate()


def test_tampered_record_is_rejected_by_release_evaluation():
    original = _bundle()
    changed = replace(original.records[0], run_id="attacker-run")
    tampered = replace(original, records=(changed,) + original.records[1:])
    decision = evaluate_evidence_bundle(tampered, _required())
    assert not decision.ready
    assert decision.failures == ("evidence bundle integrity validation failed",)


def test_tampered_commit_is_rejected_by_release_evaluation():
    original = _bundle()
    changed = replace(original.records[0], commit_sha="b" * 40)
    tampered = replace(original, records=(changed,) + original.records[1:])
    decision = evaluate_evidence_bundle(tampered, _required())
    assert not decision.ready
    assert decision.failures == ("evidence bundle integrity validation failed",)


def test_evidence_canonical_encoding_has_no_delimiter_collision():
    base = _bundle().records[0]
    left = replace(base, source="alpha|beta", run_id="gamma")
    right = replace(base, source="alpha", run_id="beta|gamma")
    assert ReleaseEvidenceBundle._canonical((left,)) != ReleaseEvidenceBundle._canonical((right,))


def test_bundle_validate_rejects_empty_records_even_with_matching_empty_hash():
    from hashlib import sha256
    empty_id = sha256(ReleaseEvidenceBundle._canonical(()).encode("utf-8")).hexdigest()
    forged = ReleaseEvidenceBundle((), empty_id)
    with pytest.raises(ValueError, match="non-empty"):
        forged.validate()


def test_bundle_validate_rejects_noncanonical_bundle_id_case():
    original = _bundle()
    forged = replace(original, bundle_id=original.bundle_id.upper())
    with pytest.raises(ValueError, match="normalized SHA-256"):
        forged.validate()
