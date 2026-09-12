from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.release_evidence import EvidenceRecord, ReleaseEvidenceBundle, evaluate_evidence_bundle
from core.release_gate import ReleaseEvidence


def _required() -> ReleaseEvidence:
    return ReleaseEvidence(True, True, True, True, True, True, True, True, True, True)


def _bundle() -> ReleaseEvidenceBundle:
    names = (
        "ci_green", "tests_green", "data_integrity_validated", "walk_forward_passed",
        "robustness_passed", "paper_trading_validated", "security_reviewed",
        "execution_reconciled", "shadow_validated", "recovery_validated",
    )
    records = tuple(
        EvidenceRecord(name, True, "validated-test", "run-001", datetime(2026, 9, 12, tzinfo=timezone.utc))
        for name in names
    )
    return ReleaseEvidenceBundle.from_records(records)


def test_bundle_requires_nonempty_records():
    with pytest.raises(ValueError):
        ReleaseEvidenceBundle.from_records(())


def test_record_requires_provenance():
    with pytest.raises(ValueError):
        EvidenceRecord("ci_green", True, "", "run-1", datetime.now(timezone.utc)).validate()


def test_unknown_evidence_name_is_rejected():
    with pytest.raises(ValueError):
        EvidenceRecord("invented_flag", True, "test", "run-1", datetime.now(timezone.utc)).validate()


def test_duplicate_evidence_name_is_rejected():
    record = EvidenceRecord("ci_green", True, "test", "run-1", datetime.now(timezone.utc))
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
    records[0] = EvidenceRecord("ci_green", False, "validated-test", "run-001", datetime(2026, 9, 12, tzinfo=timezone.utc))
    bundle = ReleaseEvidenceBundle.from_records(tuple(records))
    decision = evaluate_evidence_bundle(bundle, _required())
    assert not decision.ready
    assert decision.failures == ("required evidence failed: ci_green",)


def test_bundle_id_is_order_independent_for_same_records():
    first = _bundle()
    second = ReleaseEvidenceBundle.from_records(tuple(reversed(first.records)))
    assert first.bundle_id == second.bundle_id


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
