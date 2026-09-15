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
        """Reject incomplete or non-finite economics before performance is computed."""
        if not isfinite(float(self.pip_size)) or self.pip_size <= 0:
            raise ValueError("pip_size must be finite and positive")
        if not isfinite(float(self.volume)) or self.volume <= 0:
            raise ValueError("volume must be finite and positive")
        if not isfinite(float(self.spread)) or self.spread < 0:
            raise ValueError("spread must be finite and non-negative")
        if not isfinite(float(self.slippage)) or self.slippage < 0:
            raise ValueError("slippage must be finite and non-negative")
        if self.point_value is None:
            raise ValueError("point_value must be explicitly provided for performance backtests")
        if not isfinite(float(self.point_value)) or self.point_value <= 0:
            raise ValueError("point_value must be finite and positive")
        if not isfinite(float(self.commission_per_volume)) or self.commission_per_volume < 0:
            raise ValueError("commission_per_volume must be finite and non-negative")
        if not isinstance(self.timeframe, Timeframe):
            raise ValueError("timeframe must be a Timeframe")


def to_backtest_bars(bars: Sequence[ResearchBar], spread: float = 0.0) -> tuple[BacktestBar, ...]:
    """Convert research OHLCV bars to execution bars without using volume."""
    if spread < 0:
        raise ValueError("spread must be non-negative")
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
) -> tuple[BacktestOrder, ...]:
    """Generate only completed, causal signals and convert them to orders."""
    if not isinstance(config.timeframe, Timeframe):
        raise ValueError("timeframe must be a Timeframe")
    signals = detect_breakout_retest(bars, pip_size=config.pip_size, config=config.signal)
    return tuple(
        signal.to_backtest_order(volume=config.volume, selected_frame=config.timeframe)
        for signal in signals
    )


def run_breakout_retest_backtest(
    bars: Sequence[ResearchBar],
    config: BreakoutRetestBacktestConfig,
) -> BacktestResult:
    """Run the real SHREEK backtest engine with explicit economics only."""
    config.validate()
    execution_bars = to_backtest_bars(bars, spread=config.spread)
    orders = build_breakout_retest_orders(bars, config)
    costs = CostModel(
        slippage=config.slippage,
        point_value=config.point_value,
        commission_per_volume=config.commission_per_volume,
    )
    return run_backtest(execution_bars, orders, costs=costs)
