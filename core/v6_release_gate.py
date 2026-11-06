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


def _validated_evidence(
    bundle: ReleaseEvidenceBundle,
    expected_commit_sha: str,
) -> Mapping[str, bool]:
    if not isinstance(bundle, ReleaseEvidenceBundle):
        raise TypeError("V6 release requires ReleaseEvidenceBundle")
    bundle.validate_for_commit(expected_commit_sha)
    return bundle.as_map()


def evaluate_v6_release(
    bundle: ReleaseEvidenceBundle,
    expected_commit_sha: str | None = None,
) -> V6ReleaseDecision:
    """Return a fail-closed V6 decision bound to a trusted checkout SHA."""
    if not isinstance(bundle, ReleaseEvidenceBundle):
        live = LiveAuthorization(False, REQUIRED_EVIDENCE)
        return V6ReleaseDecision(False, live, ("evidence bundle integrity validation failed",))
    if expected_commit_sha is None:
        live = LiveAuthorization(False, REQUIRED_EVIDENCE)
        return V6ReleaseDecision(False, live, ("trusted expected commit SHA is required",))
    try:
        evidence = _validated_evidence(bundle, expected_commit_sha)
    except (TypeError, ValueError, OverflowError) as exc:
        live = LiveAuthorization(False, REQUIRED_EVIDENCE)
        failure = (
            "evidence bundle commit SHA does not match expected commit"
            if str(exc) == "evidence bundle commit SHA does not match expected commit"
            else "evidence bundle integrity validation failed"
        )
        return V6ReleaseDecision(False, live, (failure,))
    live = evaluate_live_authorization(evidence)
    failures = tuple(f"missing/failed evidence: {item}" for item in live.missing)
    return V6ReleaseDecision(live.authorized, live, failures)


def require_v6_release(
    bundle: ReleaseEvidenceBundle,
    expected_commit_sha: str | None = None,
) -> None:
    """Raise when trusted commit binding or any V6 prerequisite is absent."""
    decision = evaluate_v6_release(bundle, expected_commit_sha)
    if not decision.release_ready:
        raise RuntimeError("V6 release blocked; " + "; ".join(decision.failures))
