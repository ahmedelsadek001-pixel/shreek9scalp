"""Final deterministic release certification for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from core.release_evidence import ReleaseEvidenceBundle, evaluate_evidence_bundle
from core.release_gate import ReleaseDecision, ReleaseEvidence


@dataclass(frozen=True)
class CertificationResult:
    ready: bool
    bundle_id: str
    failures: tuple[str, ...]
    commit_sha: str | None = None


def _valid_sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def certify_release(
    bundle: ReleaseEvidenceBundle,
    required: ReleaseEvidence,
    *,
    metadata: Mapping[str, str] | None = None,
    expected_commit_sha: str | None = None,
) -> CertificationResult:
    """Produce the single release decision used by final V5.1 certification.

    Metadata is descriptive only. The result always carries the evidence commit
    so a release manifest can prove it describes the exact certified source.
    """
    if not isinstance(bundle, ReleaseEvidenceBundle):
        raise TypeError("bundle must be ReleaseEvidenceBundle")
    if not isinstance(required, ReleaseEvidence):
        raise TypeError("required must be ReleaseEvidence")
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        if any(type(k) is not str or type(v) is not str for k, v in metadata.items()):
            raise TypeError("certification metadata must contain string keys and values")
    if expected_commit_sha is not None and not _valid_sha(expected_commit_sha):
        raise ValueError("expected_commit_sha must be a 40-character hexadecimal SHA")

    try:
        bundle_commit_sha = bundle.commit_sha
        bundle_id = bundle.bundle_id
    except (TypeError, ValueError, OverflowError, AttributeError):
        return CertificationResult(
            False,
            getattr(bundle, "bundle_id", ""),
            ("evidence bundle integrity validation failed",),
            None,
        )

    if expected_commit_sha is not None and bundle_commit_sha != expected_commit_sha.lower():
        return CertificationResult(
            False,
            bundle_id,
            ("evidence commit does not match expected release commit",),
            bundle_commit_sha,
        )

    decision: ReleaseDecision = evaluate_evidence_bundle(bundle, required)
    return CertificationResult(
        decision.ready,
        bundle_id,
        decision.failures,
        bundle_commit_sha,
    )
