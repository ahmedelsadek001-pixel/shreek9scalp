"""V6.0 release gate combining safety evidence and live authorization.

This module is a policy boundary only. It does not perform live execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from core.live_authorization import LiveAuthorization, evaluate_live_authorization


@dataclass(frozen=True)
class V6ReleaseDecision:
    release_ready: bool
    live: LiveAuthorization
    failures: tuple[str, ...]


def evaluate_v6_release(evidence: Mapping[str, bool]) -> V6ReleaseDecision:
    """Return a fail-closed V6 decision from explicit evidence only."""
    live = evaluate_live_authorization(evidence)
    failures = tuple(f"missing evidence: {item}" for item in live.missing)
    return V6ReleaseDecision(live.authorized, live, failures)


def require_v6_release(evidence: Mapping[str, bool]) -> None:
    """Raise when any V6 live-release prerequisite is absent or false."""
    decision = evaluate_v6_release(evidence)
    if not decision.release_ready:
        raise RuntimeError("V6 release blocked; " + "; ".join(decision.failures))
