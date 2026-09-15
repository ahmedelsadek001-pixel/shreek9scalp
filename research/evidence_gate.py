"""Fail-closed research evidence gate for SHREEK V5.2.

This gate evaluates documented OOS evidence only. It does not authorize live
execution, broker access, or deployment.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from research.evidence_report import OOSEvidenceReport


@dataclass(frozen=True)
class EvidenceGatePolicy:
    """Minimum OOS evidence required before research can be marked robust."""

    min_oos_trades: int = 30
    min_expectancy: float = 0.0
    min_oos_stability_pct: float = 60.0
    max_ruin_rate_pct: float = 0.0
    max_worst_drawdown: float = float("inf")

    def validate(self) -> None:
        if type(self.min_oos_trades) is not int or self.min_oos_trades <= 0:
            raise ValueError("min_oos_trades must be a positive integer")
        numeric = (
            self.min_expectancy,
            self.min_oos_stability_pct,
            self.max_ruin_rate_pct,
            self.max_worst_drawdown,
        )
        if not isfinite(self.min_expectancy):
            raise ValueError("min_expectancy must be finite")
        if not isfinite(self.min_oos_stability_pct) or not 0 <= self.min_oos_stability_pct <= 100:
            raise ValueError("min_oos_stability_pct must be between 0 and 100")
        if not isfinite(self.max_ruin_rate_pct) or self.max_ruin_rate_pct < 0:
            raise ValueError("max_ruin_rate_pct must be finite and non-negative")
        if self.max_worst_drawdown < 0 or not (
            isfinite(self.max_worst_drawdown) or self.max_worst_drawdown == float("inf")
        ):
            raise ValueError("max_worst_drawdown must be non-negative")
        if any(isinstance(value, bool) for value in numeric):
            raise ValueError("policy numeric values must not be bool")


@dataclass(frozen=True)
class EvidenceGateResult:
    """Immutable research-only gate result."""

    passed: bool
    failures: tuple[str, ...]


def evaluate_oos_evidence(
    report: OOSEvidenceReport,
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
) -> EvidenceGateResult:
    """Apply conservative gates to a validated OOS evidence report.

    A pass means the supplied research evidence meets the configured research
    thresholds. It is never a live-trading authorization.
    """
    if not isinstance(report, OOSEvidenceReport):
        raise ValueError("report must be an OOSEvidenceReport")
    report.validate()
    policy.validate()
    failures: list[str] = []
    if report.oos_trade_count < policy.min_oos_trades:
        failures.append("OOS trade count below minimum")
    if report.oos_expectancy < policy.min_expectancy:
        failures.append("OOS expectancy below minimum")
    if report.oos_stability_pct < policy.min_oos_stability_pct:
        failures.append("OOS stability below minimum")
    if report.ruin_rate_pct > policy.max_ruin_rate_pct:
        failures.append("Monte Carlo ruin rate above maximum")
    if report.worst_max_drawdown > policy.max_worst_drawdown:
        failures.append("worst OOS Monte Carlo drawdown above maximum")
    return EvidenceGateResult(not failures, tuple(failures))
