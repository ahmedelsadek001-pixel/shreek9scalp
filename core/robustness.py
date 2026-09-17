"""Combined robustness gates for SHREEK V5.1 validation."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from core.risk_simulation import RobustnessSummary, monte_carlo
from core.walk_forward import WalkForwardSummary


@dataclass(frozen=True)
class RobustnessPolicy:
    min_wfo_stability_pct: float = 60.0
    max_ruin_rate_pct: float = 0.0
    max_monte_carlo_drawdown: float = float("inf")

    def validate(self) -> None:
        if not isfinite(self.min_wfo_stability_pct) or not 0 <= self.min_wfo_stability_pct <= 100:
            raise ValueError("min_wfo_stability_pct must be between 0 and 100")
        if not isfinite(self.max_ruin_rate_pct) or self.max_ruin_rate_pct < 0:
            raise ValueError("max_ruin_rate_pct must be finite and non-negative")
        if self.max_monte_carlo_drawdown < 0 or not (
            isfinite(self.max_monte_carlo_drawdown) or self.max_monte_carlo_drawdown == float("inf")
        ):
            raise ValueError("max_monte_carlo_drawdown must be non-negative")


@dataclass(frozen=True)
class RobustnessReport:
    wfo: WalkForwardSummary
    monte_carlo: RobustnessSummary
    passed: bool
    failures: tuple[str, ...]


def _validate_wfo(summary: WalkForwardSummary) -> None:
    """Reject incomplete or internally inconsistent WFO evidence before gating."""
    if not isinstance(summary, WalkForwardSummary):
        raise TypeError("wfo must be a WalkForwardSummary")
    if not summary.windows:
        raise ValueError("WFO evidence must contain at least one window")
    if (
        not isfinite(float(summary.aggregate_test_score))
        or not isfinite(float(summary.median_test_score))
        or not isfinite(float(summary.stability_pct))
        or not 0 <= summary.stability_pct <= 100
        or type(summary.positive_test_windows) is not int
        or not 0 <= summary.positive_test_windows <= len(summary.windows)
    ):
        raise ValueError("WFO summary contains invalid aggregate evidence")

    previous_test_end = None
    for result in summary.windows:
        window = result.window
        if not (
            type(window.train_start) is int
            and type(window.train_end) is int
            and type(window.test_start) is int
            and type(window.test_end) is int
            and 0 <= window.train_start < window.train_end <= window.test_start < window.test_end
            and isfinite(float(result.train_score))
            and isfinite(float(result.test_score))
        ):
            raise ValueError("WFO window contains invalid or overlapping train/test boundaries")
        if previous_test_end is not None and window.test_start < previous_test_end:
            raise ValueError("WFO window contains overlapping OOS test periods")
        previous_test_end = window.test_end


def build_robustness_report(
    wfo: WalkForwardSummary,
    pnl: Sequence[float],
    starting_equity: float = 10000.0,
    simulations: int = 1000,
    seed: int = 42,
    policy: RobustnessPolicy = RobustnessPolicy(),
) -> RobustnessReport:
    """Evaluate WFO stability and Monte Carlo tail-risk gates without execution."""
    _validate_wfo(wfo)
    policy.validate()
    mc = monte_carlo(pnl, starting_equity, simulations, seed)
    failures = []
    if wfo.stability_pct < policy.min_wfo_stability_pct:
        failures.append("WFO stability below minimum")
    if mc.ruin_rate_pct > policy.max_ruin_rate_pct:
        failures.append("Monte Carlo ruin rate above maximum")
    if mc.worst_max_drawdown > policy.max_monte_carlo_drawdown:
        failures.append("Monte Carlo drawdown above maximum")
    return RobustnessReport(wfo, mc, not failures, tuple(failures))
