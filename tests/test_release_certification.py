from datetime import datetime, timezone

import pytest

from core.release_certification import certify_release
from core.release_evidence import EvidenceRecord, ReleaseEvidenceBundle
from core.release_gate import ReleaseEvidence


_NAMES = (
    "ci_green", "tests_green", "data_integrity_validated", "walk_forward_passed",
    "robustness_passed", "paper_trading_validated", "security_reviewed",
    "execution_reconciled", "shadow_validated", "recovery_validated",
)
_COMMIT = "a" * 40
_OTHER_COMMIT = "b" * 40


def _bundle(passed: bool = True, commit_sha: str = _COMMIT) -> ReleaseEvidenceBundle:
    records = tuple(
        EvidenceRecord(name, passed, "validated-stage", "run-001", datetime(2026, 9, 12, tzinfo=timezone.utc), commit_sha)
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


def test_certification_requires_matching_expected_commit():
    result = certify_release(_bundle(), _required(), expected_commit_sha=_COMMIT)
    assert result.ready


def test_certification_blocks_stale_commit_evidence():
    result = certify_release(_bundle(), _required(), expected_commit_sha=_OTHER_COMMIT)
    assert not result.ready
    assert result.failures == ("evidence commit does not match expected release commit",)


def test_certification_rejects_invalid_expected_commit():
    with pytest.raises(ValueError, match="expected_commit_sha"):
        certify_release(_bundle(), _required(), expected_commit_sha="not-a-sha")
