from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.live_authorization import REQUIRED_EVIDENCE
from core.release_evidence import EvidenceRecord, ReleaseEvidenceBundle
from core.v6_release_gate import evaluate_v6_release, require_v6_release


def full_bundle(passed=True):
    now = datetime.now(timezone.utc)
    records = tuple(
        EvidenceRecord(
            name=name,
            passed=passed,
            source="tests.test_v6_release_gate",
            run_id="v6-test-run-001",
            recorded_at=now,
        )
        for name in REQUIRED_EVIDENCE
    )
    return ReleaseEvidenceBundle.from_records(records)


def test_v6_release_ready_with_complete_provenance():
    decision = evaluate_v6_release(full_bundle())
    assert decision.release_ready is True
    assert decision.failures == ()


def test_v6_release_fails_closed_on_failed_evidence():
    bundle = full_bundle()
    records = tuple(
        EvidenceRecord(r.name, False if r.name == "robustness_passed" else r.passed,
                       r.source, r.run_id, r.recorded_at)
        for r in bundle.records
    )
    decision = evaluate_v6_release(ReleaseEvidenceBundle.from_records(records))
    assert decision.release_ready is False
    assert any("robustness_passed" in item for item in decision.failures)
    with pytest.raises(RuntimeError):
        require_v6_release(ReleaseEvidenceBundle.from_records(records))


def test_v6_release_blocks_raw_boolean_mapping():
    decision = evaluate_v6_release({name: True for name in REQUIRED_EVIDENCE})
    assert decision.release_ready is False
    assert decision.live.authorized is False
    assert decision.failures == ("evidence bundle integrity validation failed",)


def test_v6_release_requires_all_provenance_records():
    bundle = full_bundle()
    incomplete = ReleaseEvidenceBundle.from_records(bundle.records[:-1])
    decision = evaluate_v6_release(incomplete)
    assert decision.release_ready is False
    assert "operator_approval" in decision.failures[0]


def test_v6_release_evaluation_blocks_tampered_bundle_without_raising():
    bundle = full_bundle()
    tampered = replace(bundle, bundle_id="0" * 64)
    decision = evaluate_v6_release(tampered)
    assert decision.release_ready is False
    assert decision.live.authorized is False
    assert decision.failures == ("evidence bundle integrity validation failed",)
    with pytest.raises(RuntimeError):
        require_v6_release(tampered)
