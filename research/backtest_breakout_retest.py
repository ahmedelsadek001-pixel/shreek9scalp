"""Causal Breakout + Retest research adapter for the backtest engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.backtest_engine import BacktestBar, BacktestOrder, BacktestResult, run_backtest
from research.breakout_retest import BreakoutRetestConfig, ResearchBar, detect_breakout_retest


@dataclass(frozen=True)
class BreakoutRetestBacktestConfig:
    """Execution assumptions kept separate from signal-generation rules."""

    pip_size: float
    volume: float = 1.0
    spread: float = 0.0
    slippage: float = 0.0
    point_value: float = 1.0
    commission_per_volume: float = 0.0
    signal: BreakoutRetestConfig = BreakoutRetestConfig()


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
    signals = detect_breakout_retest(bars, pip_size=config.pip_size, config=config.signal)
    return tuple(signal.to_backtest_order(volume=config.volume) for signal in signals)


def run_breakout_retest_backtest(
    bars: Sequence[ResearchBar],
    config: BreakoutRetestBacktestConfig,
) -> BacktestResult:
    """Run the real SHREEK backtest engine on Breakout + Retest signals."""
    execution_bars = to_backtest_bars(bars, spread=config.spread)
    orders = build_breakout_retest_orders(bars, config)
    return run_backtest(
        execution_bars,
        orders,
        slippage=config.slippage,
        point_value=config.point_value,
        commission_per_volume=config.commission_per_volume,
    )
