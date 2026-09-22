"""Fail-closed V5.2 research certification gate.

Certification combines independent OOS sample sufficiency, walk-forward
stability, sampling uncertainty, dependence-aware bootstrap evidence, and
Monte Carlo tail risk. It never grants execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from core.block_bootstrap import BlockBootstrapSummary
from core.research_metrics import calculate_research_metrics
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

    def validate(self) -> None:
        if type(self.passed) is not bool:
            raise ValueError("certification passed must be bool")
        if type(self.failures) is not tuple or any(
            type(item) is not str or not item for item in self.failures
        ):
            raise ValueError("certification failures must be non-empty strings")
        if self.passed != (len(self.failures) == 0):
            raise ValueError("certification pass state is inconsistent with failures")
        if type(self.oos_trades) is not int or self.oos_trades < 1:
            raise ValueError("certification OOS trades must be positive")
        if type(self.oos_windows) is not int or self.oos_windows < 1:
            raise ValueError("certification OOS windows must be positive")
        if type(self.oos_stability_pct) not in (int, float) or not isfinite(self.oos_stability_pct):
            raise ValueError("certification OOS stability must be finite")
        if not 0.0 <= self.oos_stability_pct <= 100.0:
            raise ValueError("certification OOS stability must be between 0 and 100")


def _validate_wfo_evidence(wfo: BacktestWFOResult) -> None:
    """Reject structurally inconsistent or tampered WFO evidence."""
    windows = wfo.validation.windows
    count = len(windows)
    if count == 0:
        raise ValueError("WFO must contain at least one OOS window")
    if not (
        len(wfo.validation.train_scores)
        == len(wfo.validation.test_scores)
        == len(wfo.validation.selected_parameters)
        == len(wfo.train_metrics)
        == len(wfo.oos_metrics)
        == len(wfo.oos_results)
        == count
    ):
        raise ValueError("WFO evidence cardinality is inconsistent")

    for metric, result in zip(wfo.oos_metrics, wfo.oos_results):
        expected = calculate_research_metrics(result)
        numeric_pairs = (
            (metric.win_rate_pct, expected.win_rate_pct),
            (metric.net_pnl, expected.net_pnl),
            (metric.expectancy, expected.expectancy),
            (metric.profit_factor, expected.profit_factor),
            (metric.average_win, expected.average_win),
            (metric.average_loss, expected.average_loss),
            (metric.payoff_ratio, expected.payoff_ratio),
            (metric.max_drawdown, expected.max_drawdown),
            (metric.max_drawdown_pct, expected.max_drawdown_pct),
            (metric.sharpe, expected.sharpe),
        )
        counts_match = (
            metric.trades == expected.trades
            and metric.wins == expected.wins
            and metric.losses == expected.losses
        )
        if not counts_match or any(
            not isclose(float(actual), float(wanted), rel_tol=1e-12, abs_tol=1e-12)
            for actual, wanted in numeric_pairs
        ):
            raise ValueError("WFO OOS metrics do not match OOS backtest results")


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
    _validate_wfo_evidence(wfo)

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
    result = ResearchCertification(not failures, tuple(failures), len(pnl), windows, stability)
    result.validate()
    return result
