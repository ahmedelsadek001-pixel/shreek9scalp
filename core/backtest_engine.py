"""Causal backtest engine with deterministic partial-exit lifecycle support."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite, sqrt
from typing import Iterable, Optional, Sequence

from core.enums import Direction
from core.models import ExecutionLevels
from core.position_lifecycle import LifecyclePolicy, LifecycleState, initial_state, trailing_stop_price
from core.trading_window import TradingWindowPolicy


class IntrabarPolicy(str, Enum):
    """Policy for bars that touch both stop and target without tick ordering."""
    STOP_FIRST = "STOP_FIRST"
    TARGET_FIRST = "TARGET_FIRST"
    SKIP_AMBIGUOUS = "SKIP_AMBIGUOUS"


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
        return (
            all(isfinite(float(x)) for x in values)
            and self.low <= self.high
            and self.low <= self.open <= self.high
            and self.low <= self.close <= self.high
            and self.spread >= 0
        )


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
    lifecycle_events: tuple[str, ...] = ()


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
        return (
            all(isfinite(float(x)) for x in values)
            and self.slippage >= 0
            and self.point_value > 0
            and self.commission_per_volume >= 0
        )


def _validate_timestamp(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")


def _validate_timestamp_compatibility(series: Sequence[BacktestBar], timestamp: datetime, name: str) -> None:
    _validate_timestamp(timestamp, name)
    reference = series[0].timestamp
    if (reference.tzinfo is None) != (timestamp.tzinfo is None):
        raise ValueError(f"{name} timezone awareness must match bar timestamps")


def _validate_levels(direction: Direction, levels: ExecutionLevels) -> None:
    values = (levels.entry, levels.sl, levels.tp1, levels.tp2, levels.tp3, levels.risk)
    if not all(isfinite(float(x)) and float(x) > 0 for x in values):
        raise ValueError("execution levels must be finite and positive")
    if direction == Direction.BUY:
        valid = levels.sl < levels.entry < levels.tp1 <= levels.tp2 <= levels.tp3
    elif direction == Direction.SELL:
        valid = levels.sl > levels.entry > levels.tp1 >= levels.tp2 >= levels.tp3
    else:
        valid = False
    if not valid or abs(abs(levels.entry - levels.sl) - levels.risk) > max(1e-9, levels.risk * 1e-6):
        raise ValueError("execution levels are inconsistent with order direction")


def _fill_price(bar: BacktestBar, direction: Direction, slippage: float) -> float:
    half = bar.spread / 2
    return bar.open + half + slippage if direction == Direction.BUY else bar.open - half - slippage


def _exit_price(bar: BacktestBar, direction: Direction, price: float, slippage: float) -> float:
    half = bar.spread / 2
    return price - slippage - half if direction == Direction.BUY else price + slippage + half


def _execution_cost(raw_price: float, actual_price: float, volume: float, point_value: float) -> float:
    return abs(actual_price - raw_price) * volume * point_value


def _hit(bar: BacktestBar, direction: Direction, stop: float, target: float,
         intrabar_policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST) -> Optional[tuple[float, str]]:
    try:
        policy = IntrabarPolicy(intrabar_policy)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid intrabar policy") from exc
    stop_hit = bar.low <= stop if direction == Direction.BUY else bar.high >= stop
    target_hit = bar.high >= target if direction == Direction.BUY else bar.low <= target
    if stop_hit and target_hit:
        if policy == IntrabarPolicy.STOP_FIRST:
            return stop, "SL"
        if policy == IntrabarPolicy.TARGET_FIRST:
            return target, "TP"
        return None
    if stop_hit:
        return stop, "SL"
    if target_hit:
        return target, "TP"
    return None


def _pnl(entry: float, exit_price: float, direction: Direction, volume: float, point_value: float) -> float:
    move = exit_price - entry if direction == Direction.BUY else entry - exit_price
    return move * volume * point_value


def _stats(start: float, equity: Sequence[float], trades: Sequence[BacktestTrade]) -> BacktestStats:
    end = equity[-1] if equity else start
    net = end - start
    wins = sum(t.net_pnl > 0 for t in trades)
    losses = sum(t.net_pnl < 0 for t in trades)
    gross_profit = sum(max(t.net_pnl, 0) for t in trades)
    gross_loss = sum(-min(t.net_pnl, 0) for t in trades)
    profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0)
    peak = start
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, peak - value)
    returns = []
    previous = start
    for value in equity:
        if previous:
            returns.append((value - previous) / previous)
        previous = value
    mean = sum(returns) / len(returns) if returns else 0
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0
    sharpe = mean / sqrt(variance) * sqrt(252) if variance > 0 else 0
    return BacktestStats(start, end, net, net / start * 100, len(trades), wins, losses,
                         wins / len(trades) * 100 if trades else 0, profit_factor,
                         net / len(trades) if trades else 0, drawdown,
                         drawdown / start * 100, sharpe)


def _close_at_bar(bar: BacktestBar, direction: Direction, raw_entry: float, volume: float,
                  costs: CostModel, raw_price: float) -> tuple[float, float, float]:
    exit_price = _exit_price(bar, direction, raw_price, costs.slippage)
    gross = _pnl(raw_entry, raw_price, direction, volume, costs.point_value)
    execution_cost = _execution_cost(raw_price, exit_price, volume, costs.point_value)
    commission = costs.commission_per_volume * volume
    return exit_price, gross, execution_cost + commission


def _run_lifecycle(series: Sequence[BacktestBar], order: BacktestOrder, entry_index: int,
                   entry: float, costs: CostModel, policy: LifecyclePolicy,
                   trading_window: Optional[TradingWindowPolicy] = None,
                   force_close_at_end: bool = True,
                   intrabar_policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST
                   ) -> tuple[Optional[int], Optional[float], str, float, float, float, tuple[str, ...]]:
    policy.validate()
    if trading_window is not None:
        trading_window.validate()
    state: LifecycleState = initial_state(order.volume, order.levels, policy)
    remaining = order.volume
    raw_entry = series[entry_index].open
    gross_total = 0.0
    entry_cost = _execution_cost(raw_entry, entry, order.volume, costs.point_value)
    entry_cost += costs.commission_per_volume * order.volume
    exit_cost_total = 0.0
    events: list[str] = []
    entry_time = series[entry_index].timestamp
    stages = (("TP1", order.levels.tp1), ("TP2", order.levels.tp2), ("TP3", order.levels.tp3))
    stage_index = 0
    index = entry_index
    while index < len(series) and remaining > 0:
        bar = series[index]
        if trading_window is not None and trading_window.holding_expired(entry_time, bar.timestamp):
            exit_price, gross, cost = _close_at_bar(bar, order.direction, raw_entry, remaining, costs, bar.open)
            return index, exit_price, "TIME", gross_total + gross, entry_cost + exit_cost_total + cost, remaining, tuple(events)
        stop = state.stop_price if state.stop_price is not None else order.levels.sl
        if state.trailing_active and index > entry_index:
            trail = trailing_stop_price(state, order.levels, series[index - 1].close, policy)
            stop = max(stop, trail) if order.direction == Direction.BUY else min(stop, trail)
            state = LifecycleState(state.remaining_volume, state.closed_tp1, state.closed_tp2,
                                   state.closed_tp3, state.breakeven_active, stop, state.trailing_active)
        hit = _hit(bar, order.direction, stop, stages[stage_index][1], intrabar_policy)
        if hit is None:
            index += 1
            continue
        raw_price, reason = hit
        exit_price = _exit_price(bar, order.direction, raw_price, costs.slippage)
        exit_execution_cost = _execution_cost(raw_price, exit_price, remaining, costs.point_value)
        if reason == "SL":
            exit_cost_total += exit_execution_cost + costs.commission_per_volume * remaining
            gross_total += _pnl(raw_entry, raw_price, order.direction, remaining, costs.point_value)
            return index, exit_price, "SL", gross_total, entry_cost + exit_cost_total, remaining, tuple(events)
        fraction = (policy.tp1_fraction, policy.tp2_fraction, policy.tp3_fraction)[stage_index]
        close_volume = min(remaining, order.volume * fraction)
        if close_volume <= 0:
            raise ValueError("lifecycle stage has zero executable volume")
        gross_total += _pnl(raw_entry, raw_price, order.direction, close_volume, costs.point_value)
        exit_cost_total += exit_execution_cost * (close_volume / remaining) + costs.commission_per_volume * close_volume
        remaining -= close_volume
        events.append(stages[stage_index][0])
        if stage_index == 0:
            from core.position_lifecycle import after_tp1
            state = after_tp1(state, order.levels, policy, order.volume)
        elif stage_index == 1:
            from core.position_lifecycle import after_tp2
            state = after_tp2(state, order.volume, order.levels, policy)
        else:
            return index, exit_price, "TP3", gross_total, entry_cost + exit_cost_total, 0.0, tuple(events)
        stage_index += 1
        index += 1
    if remaining > 0 and force_close_at_end and series:
        bar = series[-1]
        exit_price, gross, cost = _close_at_bar(bar, order.direction, raw_entry, remaining, costs, bar.close)
        return len(series) - 1, exit_price, "EOD", gross_total + gross, entry_cost + exit_cost_total + cost, remaining, tuple(events)
    return None, None, "", 0.0, 0.0, remaining, tuple(events)


def run_backtest(bars: Iterable[BacktestBar], orders: Iterable[BacktestOrder],
                 starting_equity: float = 10000.0, costs: CostModel = CostModel(),
                 force_close_at_end: bool = True, lifecycle_policy: Optional[LifecyclePolicy] = None,
                 trading_window: Optional[TradingWindowPolicy] = None,
                 intrabar_policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST,
                 end_index: Optional[int] = None) -> BacktestResult:
    """Run a backtest over an explicit causal execution horizon.

    ``end_index`` truncates both signal lookup and trade lifecycle evaluation.
    This prevents an OOS trade from consuming bars belonging to a later
    walk-forward window.
    """
    if not isfinite(starting_equity) or starting_equity <= 0 or not costs.valid():
        raise ValueError("invalid backtest configuration")
    try:
        intrabar_policy = IntrabarPolicy(intrabar_policy)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid intrabar policy") from exc
    if trading_window is not None:
        trading_window.validate()
    series = list(bars)
    if not series or any(not b.valid() for b in series):
        raise ValueError("invalid or empty bar series")
    for bar in series:
        _validate_timestamp(bar.timestamp, "bar timestamp")
    awareness = {bar.timestamp.tzinfo is None for bar in series}
    if len(awareness) != 1:
        raise ValueError("bar timestamp timezone awareness must be consistent")
    if any(series[i].timestamp >= series[i + 1].timestamp for i in range(len(series) - 1)):
        raise ValueError("bars must be strictly chronological")
    if end_index is not None:
        if type(end_index) is not int or end_index < 0 or end_index >= len(series):
            raise ValueError("end_index must be an integer within bars")
        series = series[: end_index + 1]
    by_time = {b.timestamp: i for i, b in enumerate(series)}
    pending = sorted(orders, key=lambda o: o.signal_time)
    for order in pending:
        _validate_timestamp_compatibility(series, order.signal_time, "order signal_time")
        if order.signal_time not in by_time:
            raise ValueError("every order must reference an existing signal bar")
        if order.direction not in (Direction.BUY, Direction.SELL):
            raise ValueError("backtest orders must be BUY or SELL")
        if not isfinite(order.volume) or order.volume <= 0:
            raise ValueError("order volume must be positive and finite")
        _validate_levels(order.direction, order.levels)
    trades = []
    equity = [starting_equity]
    occupied = -1
    for order in pending:
        signal_index = by_time[order.signal_time]
        entry_index = signal_index + 1
        if entry_index >= len(series) or entry_index <= occupied:
            continue
        entry_bar = series[entry_index]
        if trading_window is not None and not trading_window.is_open(entry_bar.timestamp):
            continue
        entry = _fill_price(entry_bar, order.direction, costs.slippage)
        if (order.direction == Direction.BUY and entry <= order.levels.sl) or (order.direction == Direction.SELL and entry >= order.levels.sl):
            continue
        if lifecycle_policy is not None:
            exit_index, exit_price, reason, gross, cost, _remaining, events = _run_lifecycle(
                series, order, entry_index, entry, costs, lifecycle_policy, trading_window,
                force_close_at_end, intrabar_policy)
            if exit_index is None:
                continue
        else:
            exit_index = None
            raw_exit = None
            reason = ""
            for i in range(entry_index, len(series)):
                if trading_window is not None and trading_window.holding_expired(entry_bar.timestamp, series[i].timestamp):
                    exit_index = i
                    raw_exit = series[i].open
                    reason = "TIME"
                    break
                hit = _hit(series[i], order.direction, order.levels.sl, order.levels.tp3, intrabar_policy)
                if hit is not None:
                    raw_exit, reason = hit
                    exit_index = i
                    break
            if exit_index is None:
                if not force_close_at_end:
                    continue
                exit_index = len(series) - 1
                raw_exit = series[-1].close
                reason = "EOD"
            exit_price, gross, exit_cost = _close_at_bar(
                series[exit_index], order.direction, entry_bar.open, order.volume, costs, raw_exit)
            entry_cost = _execution_cost(entry_bar.open, entry, order.volume, costs.point_value)
            entry_cost += costs.commission_per_volume * order.volume
            cost = entry_cost + exit_cost
            events = ()
        net = gross - cost
        trades.append(BacktestTrade(order.signal_time, entry_bar.timestamp, series[exit_index].timestamp,
                                    order.direction, entry, exit_price, order.volume, gross, cost, net,
                                    reason, order.tag, events))
        equity.append(equity[-1] + net)
        occupied = exit_index
    return BacktestResult(tuple(trades), tuple(equity), _stats(starting_equity, equity, trades))
