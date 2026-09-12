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


def certify_release(
    bundle: ReleaseEvidenceBundle,
    required: ReleaseEvidence,
    *,
    metadata: Mapping[str, str] | None = None,
    expected_commit_sha: str | None = None,
) -> CertificationResult:
    """Produce the single release decision used by final V5.1 certification.

    Metadata is descriptive only; it cannot influence readiness. When supplied,
    expected_commit_sha binds certification to the exact source commit under
    review and rejects stale evidence from another commit.
    """
    if not isinstance(bundle, ReleaseEvidenceBundle):
        raise TypeError("bundle must be ReleaseEvidenceBundle")
    if not isinstance(required, ReleaseEvidence):
        raise TypeError("required must be ReleaseEvidence")
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in metadata.items()):
            raise TypeError("certification metadata must contain string keys and values")
    if expected_commit_sha is not None:
        if not isinstance(expected_commit_sha, str) or len(expected_commit_sha) != 40:
            raise ValueError("expected_commit_sha must be a 40-character SHA")
        normalized_sha = expected_commit_sha.lower()
        if any(char not in "0123456789abcdef" for char in normalized_sha):
            raise ValueError("expected_commit_sha must contain only hexadecimal characters")
        try:
            bundle_commit_sha = bundle.commit_sha
        except (TypeError, ValueError, OverflowError):
            return CertificationResult(False, bundle.bundle_id, ("evidence bundle integrity validation failed",))
        if bundle_commit_sha != normalized_sha:
            return CertificationResult(
                False,
                bundle.bundle_id,
                ("evidence commit does not match expected release commit",),
            )
    decision: ReleaseDecision = evaluate_evidence_bundle(bundle, required)
    return CertificationResult(decision.ready, bundle.bundle_id, decision.failures)
