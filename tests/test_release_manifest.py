from dataclasses import replace

from core.release_certification import CertificationResult
from core.release_manifest import ReleaseManifest


def test_manifest_binds_certification_to_commit_and_bundle():
    result = CertificationResult(True, "b" * 64, ())
    manifest = ReleaseManifest.from_certification("V5.1-RC1", "a" * 40, result)
    assert manifest.ready
    assert manifest.commit_sha == "a" * 40
    assert manifest.bundle_id == "b" * 64
    assert len(manifest.manifest_id) == 64
    manifest.validate()


def test_manifest_is_deterministic():
    result = CertificationResult(False, "b" * 64, ("security",))
    first = ReleaseManifest.from_certification("V5.1-RC1", "a" * 40, result)
    second = ReleaseManifest.from_certification("V5.1-RC1", "a" * 40, result)
    assert first.manifest_id == second.manifest_id


def test_manifest_rejects_invalid_commit_sha():
    result = CertificationResult(True, "b" * 64, ())
    try:
        ReleaseManifest.from_certification("V5.1-RC1", "short", result)
    except ValueError as exc:
        assert "commit_sha" in str(exc)
    else:
        raise AssertionError("invalid commit SHA was accepted")


def test_manifest_rejects_non_hex_commit_sha():
    result = CertificationResult(True, "b" * 64, ())
    try:
        ReleaseManifest.from_certification("V5.1-RC1", "g" * 40, result)
    except ValueError as exc:
        assert "hexadecimal" in str(exc)
    else:
        raise AssertionError("non-hex commit SHA was accepted")


def test_manifest_rejects_malformed_bundle_id():
    result = CertificationResult(True, "not-a-sha", ())
    try:
        ReleaseManifest.from_certification("V5.1-RC1", "a" * 40, result)
    except ValueError as exc:
        assert "bundle_id" in str(exc)
    else:
        raise AssertionError("malformed bundle ID was accepted")


def test_manifest_tampering_is_detected_before_export():
    result = CertificationResult(True, "b" * 64, ())
    manifest = ReleaseManifest.from_certification("V5.1-RC1", "a" * 40, result)
    tampered = replace(manifest, ready=False)
    try:
        tampered.as_dict()
    except ValueError as exc:
        assert "manifest_id" in str(exc)
    else:
        raise AssertionError("tampered manifest was exported")


def test_manifest_rejects_ready_with_failures():
    import pytest
    from core.release_certification import CertificationResult
    with pytest.raises(ValueError, match="readiness contradicts"):
        ReleaseManifest.from_certification(
            "5.1.0", "a" * 40,
            CertificationResult(True, "b" * 64, ("hidden failure",)),
        )


def test_manifest_rejects_blocked_without_failures():
    import pytest
    from core.release_certification import CertificationResult
    with pytest.raises(ValueError, match="readiness contradicts"):
        ReleaseManifest.from_certification(
            "5.1.0", "a" * 40,
            CertificationResult(False, "b" * 64, ()),
        )


def test_manifest_validate_rejects_rehashed_semantic_contradiction():
    import pytest
    from dataclasses import replace
    from hashlib import sha256
    from core.release_certification import CertificationResult
    manifest = ReleaseManifest.from_certification(
        "5.1.0", "a" * 40,
        CertificationResult(True, "b" * 64, ()),
    )
    failures = ("tampered",)
    forged_id = sha256(
        ReleaseManifest._canonical(
            manifest.version, manifest.commit_sha, manifest.bundle_id, True, failures
        ).encode("utf-8")
    ).hexdigest()
    forged = replace(manifest, failures=failures, manifest_id=forged_id)
    with pytest.raises(ValueError, match="readiness contradicts"):
        forged.validate()


def test_manifest_rejects_commit_different_from_certified_evidence():
    import pytest
    result = CertificationResult(True, "b" * 64, (), "a" * 40)
    with pytest.raises(ValueError, match="certified evidence commit"):
        ReleaseManifest.from_certification("V5.1-RC1", "c" * 40, result)


def test_manifest_accepts_commit_bound_certification():
    result = CertificationResult(True, "b" * 64, (), "a" * 40)
    manifest = ReleaseManifest.from_certification("V5.1-RC1", "a" * 40, result)
    assert manifest.commit_sha == result.commit_sha
    manifest.validate()
