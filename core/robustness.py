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


def build_robustness_report(
    wfo: WalkForwardSummary,
    pnl: Sequence[float],
    starting_equity: float = 10000.0,
    simulations: int = 1000,
    seed: int = 42,
    policy: RobustnessPolicy = RobustnessPolicy(),
) -> RobustnessReport:
    """Evaluate WFO stability and Monte Carlo tail-risk gates without execution."""
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
