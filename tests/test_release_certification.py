from datetime import datetime, timezone

from core.release_certification import certify_release
from core.release_evidence import EvidenceRecord, ReleaseEvidenceBundle
from core.release_gate import ReleaseEvidence


_NAMES = (
    "ci_green", "tests_green", "data_integrity_validated", "walk_forward_passed",
    "robustness_passed", "paper_trading_validated", "security_reviewed",
    "execution_reconciled", "shadow_validated", "recovery_validated",
)


def _bundle(passed: bool = True) -> ReleaseEvidenceBundle:
    records = tuple(
        EvidenceRecord(name, passed, "validated-stage", "run-001", datetime(2026, 9, 12, tzinfo=timezone.utc))
        for name in _NAMES
    )
    return ReleaseEvidenceBundle.from_records(records)


def _required() -> ReleaseEvidence:
    return ReleaseEvidence(*(True for _ in _NAMES))


def test_certification_passes_only_for_complete_passing_evidence():
    result = certify_release(_bundle(), _required(), metadata={"release": "V5.1-RC1"})
    assert result.ready
    assert result.bundle_id
    assert not result.failures


def test_certification_blocks_failed_evidence():
    result = certify_release(_bundle(False), _required())
    assert not result.ready
    assert result.failures


def test_metadata_cannot_grant_release_authority():
    result = certify_release(_bundle(False), _required(), metadata={"approved": "true"})
    assert not result.ready
