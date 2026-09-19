"""Backtest-derived robustness evidence for SHREEK V5.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Sequence

from core.risk_simulation import RobustnessSummary, monte_carlo
from research.backtest_wfo import BacktestWFOResult


@dataclass(frozen=True)
class RobustnessEvidence:
    """Monte Carlo evidence derived only from realized OOS trades."""

    oos_trade_pnl: tuple[float, ...]
    starting_equity: float
    summary: RobustnessSummary
    seed: int | None = 42
    slippage_multiplier: float = 1.0
    spread_multiplier: float = 1.0

    @property
    def oos_trade_count(self) -> int:
        return len(self.oos_trade_pnl)

    def validate(self) -> None:
        """Fail closed on malformed or inconsistent reproducible evidence."""
        if not self.oos_trade_pnl:
            raise ValueError("robustness evidence requires OOS trades")
        if any(not isfinite(float(value)) for value in self.oos_trade_pnl):
            raise ValueError("robustness OOS trade P&L must be finite")
        if not isfinite(float(self.starting_equity)) or self.starting_equity <= 0:
            raise ValueError("robustness starting equity must be positive and finite")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("robustness seed must be an integer or None")
        if (
            not isfinite(float(self.slippage_multiplier))
            or not isfinite(float(self.spread_multiplier))
            or self.slippage_multiplier < 1
            or self.spread_multiplier < 1
        ):
            raise ValueError("robustness cost multipliers must be finite and >= 1")
        summary = self.summary
        if type(summary.simulations) is not int or summary.simulations <= 0:
            raise ValueError("robustness simulations must be a positive integer")
        numeric = (
            summary.ruin_rate_pct,
            summary.median_ending_equity,
            summary.worst_ending_equity,
            summary.median_max_drawdown,
            summary.worst_max_drawdown,
            summary.p05_ending_equity,
            summary.p95_max_drawdown,
        )
        if any(not isfinite(float(value)) for value in numeric):
            raise ValueError("robustness summary metrics must be finite")
        if not 0.0 <= summary.ruin_rate_pct <= 100.0:
            raise ValueError("robustness ruin rate must be between 0 and 100")
        if summary.worst_ending_equity > summary.median_ending_equity:
            raise ValueError("worst ending equity cannot exceed median ending equity")
        if summary.worst_max_drawdown < summary.median_max_drawdown:
            raise ValueError("worst drawdown cannot be below median drawdown")

        expected = monte_carlo(
            self.oos_trade_pnl,
            starting_equity=self.starting_equity,
            simulations=summary.simulations,
            seed=self.seed,
            slippage_multiplier=self.slippage_multiplier,
            spread_multiplier=self.spread_multiplier,
        )
        comparisons = (
            (summary.ruin_rate_pct, expected.ruin_rate_pct, "ruin rate"),
            (summary.median_ending_equity, expected.median_ending_equity, "median ending equity"),
            (summary.worst_ending_equity, expected.worst_ending_equity, "worst ending equity"),
            (summary.median_max_drawdown, expected.median_max_drawdown, "median drawdown"),
            (summary.worst_max_drawdown, expected.worst_max_drawdown, "worst drawdown"),
            (summary.p05_ending_equity, expected.p05_ending_equity, "p05 ending equity"),
            (summary.p95_max_drawdown, expected.p95_max_drawdown, "p95 drawdown"),
        )
        for actual, wanted, name in comparisons:
            if not isclose(float(actual), float(wanted), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"robustness {name} is inconsistent with reproducible simulation evidence")


def _extract_oos_trade_pnl(result: BacktestWFOResult) -> tuple[float, ...]:
    pnl: list[float] = []
    for backtest in result.oos_results:
        for trade in backtest.trades:
            value = float(trade.net_pnl)
            if not isfinite(value):
                raise ValueError("OOS trade P&L must be finite")
            pnl.append(value)
    if not pnl:
        raise ValueError("OOS results must contain at least one trade")
    return tuple(pnl)


def run_oos_monte_carlo(
    result: BacktestWFOResult,
    *,
    starting_equity: float,
    simulations: int = 1000,
    seed: int | None = 42,
    slippage_multiplier: float = 1.0,
    spread_multiplier: float = 1.0,
) -> RobustnessEvidence:
    """Run Monte Carlo on actual realized OOS trade P&L.

    No synthetic P&L is generated here. Trade outcomes are extracted from the
    BacktestResult objects produced by backtest-aware purged WFO. This keeps
    robustness analysis downstream of causal train/OOS validation.
    """
    if not isinstance(result, BacktestWFOResult):
        raise ValueError("result must be a BacktestWFOResult")
    pnl = _extract_oos_trade_pnl(result)
    summary = monte_carlo(
        pnl,
        starting_equity=starting_equity,
        simulations=simulations,
        seed=seed,
        slippage_multiplier=slippage_multiplier,
        spread_multiplier=spread_multiplier,
    )
    evidence = RobustnessEvidence(
        pnl,
        float(starting_equity),
        summary,
        seed,
        slippage_multiplier,
        spread_multiplier,
    )
    evidence.validate()
    return evidence
