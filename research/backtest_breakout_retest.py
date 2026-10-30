"""Causal Breakout + Retest research adapter for the backtest engine."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from core.backtest_engine import (
    BacktestBar,
    BacktestOrder,
    BacktestResult,
    CostModel,
    run_backtest,
)
from core.enums import Timeframe
from research.breakout_retest import BreakoutRetestConfig, ResearchBar, detect_breakout_retest


@dataclass(frozen=True)
class BreakoutRetestBacktestConfig:
    """Execution assumptions kept separate from signal-generation rules."""

    pip_size: float
    volume: float = 1.0
    spread: float = 0.0
    slippage: float = 0.0
    point_value: float | None = None
    commission_per_volume: float = 0.0
    timeframe: Timeframe = Timeframe.M5
    signal: BreakoutRetestConfig = BreakoutRetestConfig()

    def validate(self) -> None:
        if not isfinite(float(self.pip_size)) or self.pip_size <= 0:
            raise ValueError("pip_size must be finite and positive")
        if not isfinite(float(self.volume)) or self.volume <= 0:
            raise ValueError("volume must be finite and positive")
        if not isfinite(float(self.spread)) or self.spread < 0:
            raise ValueError("spread must be finite and non-negative")
        if not isfinite(float(self.slippage)) or self.slippage < 0:
            raise ValueError("slippage must be finite and non-negative")
        if not isinstance(self.timeframe, Timeframe):
            raise ValueError("timeframe must be a Timeframe")
        if self.point_value is None:
            raise ValueError("point_value must be explicitly provided for performance backtests")
        if not isfinite(float(self.point_value)) or self.point_value <= 0:
            raise ValueError("point_value must be finite and positive")
        if not isfinite(float(self.commission_per_volume)) or self.commission_per_volume < 0:
            raise ValueError("commission_per_volume must be finite and non-negative")
        if not isinstance(self.signal, BreakoutRetestConfig):
            raise ValueError("signal must be a BreakoutRetestConfig")
        self.signal.validate()


def to_backtest_bars(bars: Sequence[ResearchBar], spread: float = 0.0) -> tuple[BacktestBar, ...]:
    """Convert research OHLCV bars to execution bars without using volume."""
    if not isfinite(float(spread)) or spread < 0:
        raise ValueError("spread must be finite and non-negative")
    for bar in bars:
        bar.validate()
    return tuple(
        BacktestBar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            spread=spread,
        )
        for bar in bars
    )


def build_breakout_retest_orders(
    bars: Sequence[ResearchBar],
    config: BreakoutRetestBacktestConfig,
    *,
    min_signal_index: int = 0,
) -> tuple[BacktestOrder, ...]:
    """Generate causal signals while preserving an optional OOS boundary."""
    config.validate()
    if type(min_signal_index) is not int or min_signal_index < 0 or min_signal_index > len(bars):
        raise ValueError("min_signal_index must be an integer within bars")
    signals = sorted(
        detect_breakout_retest(
            bars,
            pip_size=config.pip_size,
            config=config.signal,
            min_signal_index=min_signal_index,
        ),
        key=lambda signal: (signal.signal_time, signal.breakout_time),
    )
    return tuple(
        signal.to_backtest_order(
            volume=config.volume,
            selected_frame=config.timeframe,
            rr1=config.signal.tp1_rr,
        )
        for signal in signals
    )


def run_breakout_retest_backtest(
    bars: Sequence[ResearchBar],
    config: BreakoutRetestBacktestConfig,
    *,
    min_signal_index: int = 0,
    execution_end_index: int | None = None,
) -> BacktestResult:
    """Run the real backtest engine with explicit signal and execution horizons.

    Warm-up bars may precede ``min_signal_index`` for signal context. When
    ``execution_end_index`` is supplied, both eligible signal bars and the
    entire trade lifecycle are capped at that index, preventing an OOS trade
    from consuming bars belonging to a later walk-forward window.
    """
    config.validate()
    if type(min_signal_index) is not int or min_signal_index < 0 or min_signal_index > len(bars):
        raise ValueError("min_signal_index must be an integer within bars")
    if execution_end_index is not None:
        if type(execution_end_index) is not int or execution_end_index < 0 or execution_end_index >= len(bars):
            raise ValueError("execution_end_index must be an integer within bars")
        if execution_end_index < min_signal_index:
            raise ValueError("execution_end_index must not precede min_signal_index")
    execution_bars = to_backtest_bars(bars, spread=config.spread)
    orders = build_breakout_retest_orders(
        bars,
        config,
        min_signal_index=min_signal_index,
    )
    if execution_end_index is not None:
        end_time = execution_bars[execution_end_index].timestamp
        orders = tuple(order for order in orders if order.signal_time <= end_time)
    costs = CostModel(
        slippage=config.slippage,
        point_value=config.point_value,
        commission_per_volume=config.commission_per_volume,
    )
    return run_backtest(
        execution_bars,
        orders,
        costs=costs,
        end_index=execution_end_index,
    )
