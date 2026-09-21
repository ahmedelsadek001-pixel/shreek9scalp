"""Fail-closed V5.2 research certification gate.

Certification combines independent OOS sample sufficiency, walk-forward
stability, sampling uncertainty, dependence-aware bootstrap evidence, and
Monte Carlo tail risk. It never grants execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from core.block_bootstrap import BlockBootstrapSummary
from core.statistical_evidence import MeanConfidenceInterval
from research.backtest_wfo import BacktestWFOResult
from research.robustness import RobustnessEvidence


@dataclass(frozen=True)
class ResearchCertificationPolicy:
    min_oos_trades: int = 30
    min_oos_windows: int = 3
    min_oos_stability_pct: float = 60.0
    require_positive_ci_lower: bool = True
    require_positive_bootstrap_lower: bool = True
    max_bootstrap_non_positive_rate_pct: float = 5.0
    max_ruin_rate_pct: float = 0.0

    def validate(self) -> None:
        if type(self.min_oos_trades) is not int or self.min_oos_trades < 2:
            raise ValueError("min_oos_trades must be an integer of at least two")
        if type(self.min_oos_windows) is not int or self.min_oos_windows < 1:
            raise ValueError("min_oos_windows must be a positive integer")
        if type(self.require_positive_ci_lower) is not bool or type(self.require_positive_bootstrap_lower) is not bool:
            raise ValueError("research certification switches must be bools")
        for value, name in (
            (self.min_oos_stability_pct, "min_oos_stability_pct"),
            (self.max_bootstrap_non_positive_rate_pct, "max_bootstrap_non_positive_rate_pct"),
            (self.max_ruin_rate_pct, "max_ruin_rate_pct"),
        ):
            if type(value) not in (int, float) or not isfinite(value) or not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be finite and between 0 and 100")


@dataclass(frozen=True)
class ResearchCertification:
    passed: bool
    failures: tuple[str, ...]
    oos_trades: int
    oos_windows: int
    oos_stability_pct: float


def certify_research(
    wfo: BacktestWFOResult,
    interval: MeanConfidenceInterval,
    bootstrap: BlockBootstrapSummary,
    robustness: RobustnessEvidence,
    policy: ResearchCertificationPolicy = ResearchCertificationPolicy(),
) -> ResearchCertification:
    """Combine validated evidence and fail closed on disagreement or weakness."""
    if not isinstance(wfo, BacktestWFOResult):
        raise ValueError("wfo must be a BacktestWFOResult")
    if not isinstance(interval, MeanConfidenceInterval):
        raise ValueError("interval must be a MeanConfidenceInterval")
    if not isinstance(bootstrap, BlockBootstrapSummary):
        raise ValueError("bootstrap must be a BlockBootstrapSummary")
    if not isinstance(robustness, RobustnessEvidence):
        raise ValueError("robustness must be RobustnessEvidence")
    policy.validate()
    interval.validate()
    bootstrap.validate()
    robustness.validate()

    pnl = wfo.oos_trade_pnl
    if not pnl:
        raise ValueError("WFO must contain realized OOS trades")
    if tuple(float(v) for v in pnl) != tuple(float(v) for v in robustness.oos_trade_pnl):
        raise ValueError("robustness evidence does not match WFO OOS trades")
    if interval.samples != len(pnl) or bootstrap.samples != len(pnl):
        raise ValueError("statistical evidence sample count does not match WFO OOS trades")

    observed_mean = sum(float(v) for v in pnl) / len(pnl)
    tolerance = 1e-12
    if abs(interval.mean - observed_mean) > tolerance or abs(bootstrap.observed_mean - observed_mean) > tolerance:
        raise ValueError("statistical evidence mean does not match WFO OOS trades")

    failures = []
    windows = len(wfo.oos_metrics)
    stability = wfo.oos_stability_pct
    if len(pnl) < policy.min_oos_trades:
        failures.append("insufficient OOS trades")
    if windows < policy.min_oos_windows:
        failures.append("insufficient OOS windows")
    if stability < policy.min_oos_stability_pct:
        failures.append("OOS stability below minimum")
    if observed_mean <= 0.0:
        failures.append("OOS expectancy is not positive")
    if policy.require_positive_ci_lower and interval.lower <= 0.0:
        failures.append("confidence interval does not exclude non-positive expectancy")
    if policy.require_positive_bootstrap_lower and bootstrap.lower_mean <= 0.0:
        failures.append("block bootstrap lower bound is not positive")
    if bootstrap.non_positive_mean_rate_pct > policy.max_bootstrap_non_positive_rate_pct:
        failures.append("bootstrap non-positive expectancy rate above maximum")
    if robustness.summary.ruin_rate_pct > policy.max_ruin_rate_pct:
        failures.append("Monte Carlo ruin rate above maximum")
    return ResearchCertification(not failures, tuple(failures), len(pnl), windows, stability)
