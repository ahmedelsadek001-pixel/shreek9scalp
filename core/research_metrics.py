"""Deterministic research metrics for evaluating backtest evidence."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import median
from typing import Sequence

from core.backtest_engine import BacktestResult, BacktestTrade


@dataclass(frozen=True)
class ResearchMetrics:
    """Performance metrics derived only from realized backtest trades."""

    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    net_pnl: float
    expectancy: float
    profit_factor: float
    average_win: float
    average_loss: float
    payoff_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe: float

    def validate(self) -> None:
        numeric = (
            self.win_rate_pct,
            self.net_pnl,
            self.expectancy,
            self.average_win,
            self.average_loss,
            self.max_drawdown,
            self.max_drawdown_pct,
            self.sharpe,
        )
        if not all(isfinite(float(value)) for value in numeric):
            raise ValueError("research metrics must be finite")
        if self.trades < 0 or self.wins < 0 or self.losses < 0:
            raise ValueError("research trade counts must be non-negative")
        if self.wins + self.losses > self.trades:
            raise ValueError("wins and losses cannot exceed trades")
        if self.max_drawdown < 0 or self.max_drawdown_pct < 0:
            raise ValueError("drawdown cannot be negative")


def _trade_pnl(trades: Sequence[BacktestTrade]) -> tuple[float, ...]:
    values = tuple(float(trade.net_pnl) for trade in trades)
    if any(not isfinite(value) for value in values):
        raise ValueError("trade pnl must be finite")
    return values


def _drawdown(equity: Sequence[float], starting_equity: float) -> tuple[float, float]:
    peak = starting_equity
    maximum = 0.0
    for value in equity:
        if not isfinite(float(value)):
            raise ValueError("equity curve must be finite")
        peak = max(peak, value)
        maximum = max(maximum, peak - value)
    return maximum, maximum / starting_equity * 100.0


def calculate_research_metrics(result: BacktestResult) -> ResearchMetrics:
    """Calculate research metrics without adding assumptions to the backtest."""
    if not isinstance(result, BacktestResult):
        raise ValueError("result must be a BacktestResult")
    trades = result.trades
    pnl = _trade_pnl(trades)
    count = len(pnl)
    wins = tuple(value for value in pnl if value > 0)
    losses = tuple(value for value in pnl if value < 0)
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
    average_win = median(wins) if wins else 0.0
    average_loss = -median(losses) if losses else 0.0
    payoff = average_win / average_loss if average_loss else (float("inf") if average_win else 0.0)
    max_dd, max_dd_pct = _drawdown(result.equity_curve, result.stats.starting_equity)
    returns = []
    previous = result.stats.starting_equity
    for value in result.equity_curve:
        if previous:
            returns.append((value - previous) / previous)
        previous = value
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = (
        sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        if len(returns) > 1
        else 0.0
    )
    sharpe = mean / sqrt(variance) * sqrt(252) if variance > 0 else 0.0
    metrics = ResearchMetrics(
        count,
        len(wins),
        len(losses),
        len(wins) / count * 100.0 if count else 0.0,
        sum(pnl),
        sum(pnl) / count if count else 0.0,
        profit_factor,
        average_win,
        average_loss,
        payoff,
        max_dd,
        max_dd_pct,
        sharpe,
    )
    metrics.validate()
    return metrics
