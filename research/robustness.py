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

    @property
    def oos_trade_count(self) -> int:
        return len(self.oos_trade_pnl)


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
    return RobustnessEvidence(pnl, float(starting_equity), summary)
