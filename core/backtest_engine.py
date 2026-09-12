"""Causal, event-driven historical backtest engine for SHREEK V5.1.

The strategy supplies execution levels only after a signal is generated from
closed data. Entries fill on the next bar, never on the signal bar. If a bar
touches both SL and TP, SL wins conservatively. No broker/network I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt
from typing import Iterable, Optional, Sequence

from core.enums import Direction
from core.models import ExecutionLevels


@dataclass(frozen=True)
class BacktestBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    spread: float = 0.0

    def valid(self) -> bool:
        values = (self.open, self.high, self.low, self.close, self.spread)
        return all(isfinite(float(v)) for v in values) and self.low <= self.high and self.spread >= 0


@dataclass(frozen=True)
class BacktestOrder:
    signal_time: datetime
    direction: Direction
    levels: ExecutionLevels
    volume: float = 1.0
    tag: str = ""


@dataclass(frozen=True)
class BacktestTrade:
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    direction: Direction
    entry: float
    exit: float
    volume: float
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str
    tag: str = ""


@dataclass(frozen=True)
class BacktestStats:
    starting_equity: float
    ending_equity: float
    net_pnl: float
    return_pct: float
    trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    expectancy: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe: float


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[BacktestTrade, ...]
    equity_curve: tuple[float, ...]
    stats: BacktestStats


@dataclass(frozen=True)
class CostModel:
    slippage: float = 0.0
    point_value: float = 1.0
    commission_per_volume: float = 0.0

    def valid(self) -> bool:
        values = (self.slippage, self.point_value, self.commission_per_volume)
        return all(isfinite(float(v)) for v in values) and self.slippage >= 0 and self.point_value > 0 and self.commission_per_volume >= 0


def _fill_price(bar: BacktestBar, direction: Direction, slippage: float) -> float:
    half_spread = bar.spread / 2.0
    return bar.open + half_spread + slippage if direction == Direction.BUY else bar.open - half_spread - slippage


def _exit_hit(bar: BacktestBar, direction: Direction, sl: float, tp: float) -> tuple[Optional[float], str]:
    if direction == Direction.BUY:
        stop_hit, target_hit = bar.low <= sl, bar.high >= tp
    else:
        stop_hit, target_hit = bar.high >= sl, bar.low <= tp
    if stop_hit:
        return sl, "SL"
    if target_hit:
        return tp, "TP3"
    return None, ""


def _stats(starting_equity: float, equity: Sequence[float], trades: Sequence[BacktestTrade]) -> BacktestStats:
    ending = equity[-1] if equity else starting_equity
    net = ending - starting_equity
    wins = sum(t.net_pnl > 0 for t in trades)
    losses = sum(t.net_pnl < 0 for t in trades)
    gross_profit = sum(max(t.net_pnl, 0.0) for t in trades)
    gross_loss = sum(-min(t.net_pnl, 0.0) for t in trades)
    pf = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
    peak = starting_equity
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    returns = []
    previous = starting_equity
    for value in equity:
        if previous:
            returns.append((value - previous) / previous)
        previous = value
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    sharpe = mean / sqrt(variance) * sqrt(252.0) if variance > 0 else 0.0
    return BacktestStats(
        starting_equity=starting_equity,
        ending_equity=ending,
        net_pnl=net,
        return_pct=(net / starting_equity * 100.0) if starting_equity else 0.0,
        trades=len(trades), wins=wins, losses=losses,
        win_rate=(wins / len(trades) * 100.0) if trades else 0.0,
        profit_factor=pf, expectancy=(net / len(trades)) if trades else 0.0,
        max_drawdown=max_dd,
        max_drawdown_pct=(max_dd / starting_equity * 100.0) if starting_equity else 0.0,
        sharpe=sharpe,
    )


def run_backtest(
    bars: Iterable[BacktestBar],
    orders: Iterable[BacktestOrder],
    starting_equity: float = 10_000.0,
    costs: CostModel = CostModel(),
    force_close_at_end: bool = True,
) -> BacktestResult:
    """Run a deterministic single-position backtest with causal fills."""
    if not isfinite(starting_equity) or starting_equity <= 0 or not costs.valid():
        raise ValueError("invalid backtest configuration")
    series = list(bars)
    if not series or any(not b.valid() for b in series):
        raise ValueError("invalid or empty bar series")
    if any(series[i].timestamp >= series[i + 1].timestamp for i in range(len(series) - 1)):
        raise ValueError("bars must be strictly chronological")
    by_time = {b.timestamp: i for i, b in enumerate(series)}
    pending = sorted(orders, key=lambda o: o.signal_time)
    if any(o.signal_time not in by_time for o in pending):
        raise ValueError("every order must reference an existing signal bar")
    if any(o.direction not in (Direction.BUY, Direction.SELL) for o in pending):
        raise ValueError("backtest orders must be BUY or SELL")
    if any(o.volume <= 0 or not isfinite(o.volume) for o in pending):
        raise ValueError("order volume must be positive and finite")

    trades: list[BacktestTrade] = []
    equity_curve = [starting_equity]
    occupied_until = -1
    for order in pending:
        signal_index = by_time[order.signal_time]
        entry_index = signal_index + 1
        if entry_index >= len(series) or entry_index <= occupied_until:
            continue
        entry_bar = series[entry_index]
        entry = _fill_price(entry_bar, order.direction, costs.slippage)
        if order.direction == Direction.BUY and entry <= order.levels.sl:
            continue
        if order.direction == Direction.SELL and entry >= order.levels.sl:
            continue

        exit_price: Optional[float] = None
        reason = ""
        exit_index: Optional[int] = None
        for i in range(entry_index, len(series)):
            hit, why = _exit_hit(series[i], order.direction, order.levels.sl, order.levels.tp3)
            if hit is not None:
                exit_price, reason, exit_index = hit, why, i
                break
        if exit_price is None:
            if not force_close_at_end:
                continue
            exit_index = len(series) - 1
            exit_price, reason = series[-1].close, "EOD"
        assert exit_index is not None
        half_spread = series[exit_index].spread / 2.0
        if order.direction == Direction.BUY:
            adverse_exit = exit_price - costs.slippage - half_spread
            gross = (adverse_exit - entry) * order.volume * costs.point_value
        else:
            adverse_exit = exit_price + costs.slippage + half_spread
            gross = (entry - adverse_exit) * order.volume * costs.point_value
        commission = costs.commission_per_volume * order.volume
        net = gross - commission
        trades.append(BacktestTrade(order.signal_time, entry_bar.timestamp, series[exit_index].timestamp, order.direction, entry, adverse_exit, order.volume, gross, commission, net, reason, order.tag))
        equity_curve.append(equity_curve[-1] + net)
        occupied_until = exit_index

    return BacktestResult(tuple(trades), tuple(equity_curve), _stats(starting_equity, equity_curve, trades))
