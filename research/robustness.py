"""Backtest-derived robustness evidence for SHREEK V5.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from core.risk_simulation import RobustnessSummary, monte_carlo
from research.backtest_wfo import BacktestWFOResult


@dataclass(frozen=True)
class RobustnessEvidence:
    """Monte Carlo evidence derived only from realized OOS trades."""

    oos_trade_pnl: tuple[float, ...]
    starting_equity: float
    summary: RobustnessSummary
    simulations: int = 1000
    seed: int | None = 42
    slippage_multiplier: float = 1.0
    spread_multiplier: float = 1.0

    @property
    def oos_trade_count(self) -> int:
        return len(self.oos_trade_pnl)

    def validate(self, *, require_reproducible: bool = False) -> None:
        if type(require_reproducible) is not bool:
            raise ValueError("require_reproducible must be a bool")
        if not self.oos_trade_pnl or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            for value in self.oos_trade_pnl
        ):
            raise ValueError("Monte Carlo OOS trade P&L must be non-empty and finite")
        if (
            isinstance(self.starting_equity, bool)
            or not isinstance(self.starting_equity, (int, float))
            or not isfinite(self.starting_equity)
            or self.starting_equity <= 0
        ):
            raise ValueError("Monte Carlo starting equity must be positive and finite")
        if type(self.simulations) is not int or self.simulations <= 0:
            raise ValueError("Monte Carlo simulations must be a positive integer")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("Monte Carlo seed must be an integer or None")
        if require_reproducible and self.seed is None:
            raise ValueError("a fixed Monte Carlo seed is required for an auditable export")
        for name, value in (
            ("slippage_multiplier", self.slippage_multiplier),
            ("spread_multiplier", self.spread_multiplier),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 1.0
            ):
                raise ValueError(f"{name} must be finite and >= 1")
        if self.seed is not None:
            expected = monte_carlo(
                self.oos_trade_pnl,
                starting_equity=self.starting_equity,
                simulations=self.simulations,
                seed=self.seed,
                slippage_multiplier=self.slippage_multiplier,
                spread_multiplier=self.spread_multiplier,
            )
            if expected != self.summary:
                raise ValueError("Monte Carlo summary does not match its recorded inputs")


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
    return RobustnessEvidence(
        pnl,
        float(starting_equity),
        summary,
        simulations,
        seed,
        slippage_multiplier,
        spread_multiplier,
    )
