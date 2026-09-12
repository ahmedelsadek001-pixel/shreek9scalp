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
