"""V6.0 provenance-bound release gate.

This module is a policy boundary only. It does not perform live execution.
Raw boolean evidence is intentionally rejected: V6 authorization must be
backed by a validated ReleaseEvidenceBundle with provenance records.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from core.live_authorization import REQUIRED_EVIDENCE, LiveAuthorization, evaluate_live_authorization
from core.release_evidence import ReleaseEvidenceBundle


@dataclass(frozen=True)
class V6ReleaseDecision:
    release_ready: bool
    live: LiveAuthorization
    failures: tuple[str, ...]


def _validated_evidence(bundle: ReleaseEvidenceBundle) -> Mapping[str, bool]:
    if not isinstance(bundle, ReleaseEvidenceBundle):
        raise TypeError("V6 release requires ReleaseEvidenceBundle")
    return bundle.as_map()


def evaluate_v6_release(bundle: ReleaseEvidenceBundle, *,
                        expected_commit_sha: str | None = None) -> V6ReleaseDecision:
    """Require evidence bound to the exact candidate commit being evaluated."""
    try:
        evidence = _validated_evidence(bundle)
    except (TypeError, ValueError, OverflowError):
        live = LiveAuthorization(False, REQUIRED_EVIDENCE)
        return V6ReleaseDecision(
            False,
            live,
            ("evidence bundle integrity validation failed",),
        )
    if (type(expected_commit_sha) is not str or len(expected_commit_sha) != 40
            or any(char not in "0123456789abcdef" for char in expected_commit_sha)):
        live = LiveAuthorization(False, REQUIRED_EVIDENCE)
        return V6ReleaseDecision(False, live, ("release candidate commit SHA is missing or invalid",))
    if bundle.commit_sha != expected_commit_sha:
        live = LiveAuthorization(False, REQUIRED_EVIDENCE)
        return V6ReleaseDecision(False, live, ("evidence commit SHA does not match release candidate",))
    live = evaluate_live_authorization(evidence)
    failures = tuple(f"missing/failed evidence: {item}" for item in live.missing)
    return V6ReleaseDecision(live.authorized, live, failures)


def require_v6_release(bundle: ReleaseEvidenceBundle, *,
                       expected_commit_sha: str | None = None) -> None:
    """Raise when any V6 live-release prerequisite is absent or false."""
    decision = evaluate_v6_release(bundle, expected_commit_sha=expected_commit_sha)
    if not decision.release_ready:
        raise RuntimeError("V6 release blocked; " + "; ".join(decision.failures))
