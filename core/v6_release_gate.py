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
    for record in bundle.records:
        record.validate()
    return bundle.as_map()


def evaluate_v6_release(bundle: ReleaseEvidenceBundle) -> V6ReleaseDecision:
    """Return a fail-closed V6 decision from provenance-bound evidence only."""
    try:
        evidence = _validated_evidence(bundle)
    except (TypeError, ValueError, OverflowError):
        live = LiveAuthorization(False, REQUIRED_EVIDENCE)
        return V6ReleaseDecision(
            False,
            live,
            ("evidence bundle integrity validation failed",),
        )
    live = evaluate_live_authorization(evidence)
    failures = tuple(f"missing/failed evidence: {item}" for item in live.missing)
    return V6ReleaseDecision(live.authorized, live, failures)


def require_v6_release(bundle: ReleaseEvidenceBundle) -> None:
    """Raise when any V6 live-release prerequisite is absent or false."""
    decision = evaluate_v6_release(bundle)
    if not decision.release_ready:
        raise RuntimeError("V6 release blocked; " + "; ".join(decision.failures))
