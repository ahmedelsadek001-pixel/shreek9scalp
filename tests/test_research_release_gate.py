from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from research.research_release_gate import (
    ResearchReleaseEvidence,
    ResearchReleaseEvidenceBundle,
    ResearchReleaseEvidenceRecord,
    ResearchReleaseDecision,
    evaluate_research_release,
)


COMMIT = "a" * 40
NAMES = tuple(ResearchReleaseEvidence.__dataclass_fields__)


def complete():
    return ResearchReleaseEvidence(True, True, True, True, True, True, True, True, True)


def artifact_bytes(omit=()):
    return {
        name: f"evidence-content:{name}".encode("utf-8")
        for name in NAMES
        if name not in omit
    }


def bundle(*, passed=True, omit=(), commit=COMMIT):
    contents = artifact_bytes(omit)
    records = tuple(
        ResearchReleaseEvidenceRecord.from_artifact_bytes(
            name=name,
            passed=passed if isinstance(passed, bool) else passed.get(name, True),
            source=f"tests/{name}.json",
            run_id=f"run-{name}",
            recorded_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
            commit_sha=commit,
            artifact_bytes=contents[name],
        )
        for name in contents
    )
    return ResearchReleaseEvidenceBundle.from_records(records)


def test_complete_artifact_bound_research_evidence_is_ready():
    evidence_bundle = bundle()
    result = evaluate_research_release(
        complete(),
        bundle=evidence_bundle,
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=artifact_bytes(),
    )
    assert result.ready is True
    assert result.failures == ()
    assert result.bundle_sha256 == evidence_bundle.bundle_sha256
    assert result.commit_sha == COMMIT
    result.validate()
    assert result.as_dict()["manifest_sha256"] == result.manifest_sha256


def test_decision_manifest_detects_result_tampering():
    evidence_bundle = bundle()
    decision = evaluate_research_release(
        complete(),
        bundle=evidence_bundle,
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=artifact_bytes(),
    )
    tampered = replace(decision, ready=False)
    with pytest.raises(ValueError, match="readiness disagrees"):
        tampered.validate()
    tampered = replace(decision, manifest_sha256="f" * 64)
    with pytest.raises(ValueError, match="manifest SHA-256"):
        tampered.validate()

    assert isinstance(decision, ResearchReleaseDecision)


def test_boolean_flags_without_artifact_bundle_are_not_sufficient():
    result = evaluate_research_release(complete())
    assert result.ready is False
    assert "artifact-bound research evidence bundle is missing" in result.failures


def test_missing_artifact_record_blocks_promotion():
    result = evaluate_research_release(
        complete(),
        bundle=bundle(omit=("purged_wfo_validated",)),
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=artifact_bytes(omit=("purged_wfo_validated",)),
    )
    assert result.ready is False
    assert any("missing artifact-bound research evidence: purged_wfo_validated" in item for item in result.failures)


def test_failed_artifact_blocks_promotion():
    evidence = replace(complete(), bootstrap_validated=False)
    result = evaluate_research_release(
        evidence,
        bundle=bundle(passed={"bootstrap_validated": False}),
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=artifact_bytes(),
    )
    assert result.ready is False
    assert "bootstrap expectancy validation is not validated" in result.failures
    assert "research artifact did not pass: bootstrap_validated" in result.failures


def test_mismatched_expected_commit_blocks_promotion():
    result = evaluate_research_release(
        complete(),
        bundle=bundle(),
        expected_commit_sha="b" * 40,
        artifact_bytes_by_name=artifact_bytes(),
    )
    assert result.ready is False
    assert "research evidence bundle is bound to a different commit" in result.failures


def test_unbound_expected_commit_blocks_promotion():
    result = evaluate_research_release(
        complete(), bundle=bundle(), artifact_bytes_by_name=artifact_bytes()
    )
    assert result.ready is False
    assert "expected source commit SHA is missing" in result.failures


def test_changed_artifact_bytes_block_promotion():
    contents = artifact_bytes()
    contents["mae_mfe_validated"] = b"edited after hashing"
    result = evaluate_research_release(
        complete(),
        bundle=bundle(),
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=contents,
    )
    assert result.ready is False
    assert "research artifact digest mismatch: mae_mfe_validated" in result.failures


def test_missing_artifact_bytes_block_promotion():
    result = evaluate_research_release(
        complete(),
        bundle=bundle(),
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=artifact_bytes(omit=("execution_quality_validated",)),
    )
    assert result.ready is False
    assert "research artifact bytes are missing: execution_quality_validated" in result.failures


def test_tampered_bundle_digest_blocks_promotion():
    evidence_bundle = bundle()
    tampered = replace(evidence_bundle, bundle_sha256="f" * 64)
    result = evaluate_research_release(
        complete(),
        bundle=tampered,
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=artifact_bytes(),
    )
    assert result.ready is False
    assert "research evidence bundle integrity validation failed" in result.failures


def test_bundle_rejects_duplicate_records_and_mixed_commits():
    one = bundle().records[0]
    with pytest.raises(ValueError, match="duplicate"):
        ResearchReleaseEvidenceBundle.from_records((one, one))
    other_commit = replace(one, name=NAMES[1], commit_sha="b" * 40)
    with pytest.raises(ValueError, match="same commit"):
        ResearchReleaseEvidenceBundle.from_records((one, other_commit))


def test_record_requires_sha256_artifact_digest():
    record = replace(bundle().records[0], artifact_sha256="a" * 40)
    with pytest.raises(ValueError, match="64-character SHA-256"):
        record.validate()


def test_record_factory_hashes_exact_artifact_bytes():
    record = ResearchReleaseEvidenceRecord.from_artifact_bytes(
        name="ci_green",
        passed=True,
        source="actions/run.json",
        run_id="run-123",
        recorded_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
        commit_sha=COMMIT,
        artifact_bytes=b"ci evidence",
    )
    assert record.artifact_sha256 == sha256(b"ci evidence").hexdigest()
    record.validate()


def test_non_boolean_research_evidence_fails_closed():
    with pytest.raises(TypeError):
        evaluate_research_release("bad")
    malformed = replace(complete(), ci_green=1)
    result = evaluate_research_release(
        malformed,
        bundle=bundle(),
        expected_commit_sha=COMMIT,
        artifact_bytes_by_name=artifact_bytes(),
    )
    assert result.ready is False
    assert "CI is not green" in result.failures
