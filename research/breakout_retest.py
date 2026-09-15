"""Causal, broker-neutral Breakout + Retest signal generation for research.

Rules are derived from the legacy SHREEK Breakout Confirmation specification, but
this module has no MT5, network, AI, or credential dependencies. Signals are only
formed from bars strictly before or at the confirmation bar; no future bar is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, isclose
from typing import Optional, Sequence

from core.backtest_engine import BacktestOrder
from core.enums import Direction, SetupType, Timeframe
from core.models import ExecutionLevels


@dataclass(frozen=True)
class ResearchBar:
    """OHLCV bar used by the research detector."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def validate(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume)
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("bar values must be finite")
        if self.low > self.high or not self.low <= self.open <= self.high or not self.low <= self.close <= self.high:
            raise ValueError("bar OHLC values are inconsistent")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")


@dataclass(frozen=True)
class BreakoutRetestConfig:
    """Explicit research thresholds from the legacy strategy specification."""

    consolidation_bars: int = 6
    min_range_pips: float = 20.0
    max_range_pips: float = 40.0
    breakout_body_pct: float = 0.65
    volume_lookback: int = 20
    volume_multiplier: float = 1.5
    retest_max_bars: int = 12
    sl_buffer_pips: float = 5.0
    tp1_rr: float = 1.5
    tp2_rr: float = 2.5
    tp3_rr: float = 4.0

    def validate(self) -> None:
        if type(self.consolidation_bars) is not int or self.consolidation_bars < 1:
            raise ValueError("consolidation_bars must be a positive integer")
        if type(self.volume_lookback) is not int or self.volume_lookback < 1:
            raise ValueError("volume_lookback must be a positive integer")
        if type(self.retest_max_bars) is not int or self.retest_max_bars < 1:
            raise ValueError("retest_max_bars must be a positive integer")
        finite_positive = (
            self.min_range_pips, self.max_range_pips, self.breakout_body_pct,
            self.volume_multiplier, self.sl_buffer_pips, self.tp1_rr,
            self.tp2_rr, self.tp3_rr,
        )
        if any(not isfinite(float(value)) or value <= 0 for value in finite_positive):
            raise ValueError("thresholds must be finite and positive")
        if self.min_range_pips > self.max_range_pips or self.breakout_body_pct > 1.0:
            raise ValueError("invalid range or breakout thresholds")


@dataclass(frozen=True)
class BreakoutRetestSignal:
    direction: Direction
    signal_time: datetime
    breakout_time: datetime
    breakout_level: float
    entry_price: float
    sl_price: float
    tp1: float
    tp2: float
    tp3: float
    body_pct: float
    volume_ratio: float
    confirmation: str

    def to_backtest_order(
        self,
        volume: float = 1.0,
        selected_frame: Timeframe = Timeframe.M5,
    ) -> BacktestOrder:
        if not isinstance(selected_frame, Timeframe):
            raise ValueError("selected_frame must be a Timeframe")
        risk = abs(self.entry_price - self.sl_price)
        return BacktestOrder(
            signal_time=self.signal_time,
            direction=self.direction,
            levels=ExecutionLevels(
                entry=self.entry_price,
                sl=self.sl_price,
                tp1=self.tp1,
                tp2=self.tp2,
                tp3=self.tp3,
                risk=risk,
                rr1=1.5,
                setup_type=SetupType.COMBINED,
                confidence=1.0,
                selected_frame=selected_frame,
                details="causal_breakout_retest",
            ),
            volume=volume,
            tag="breakout_retest",
        )


def _body_pct(bar: ResearchBar) -> float:
    candle_range = bar.high - bar.low
    return abs(bar.close - bar.open) / candle_range if candle_range > 0 else 0.0


def _is_bullish_pin(bar: ResearchBar) -> bool:
    candle_range = bar.high - bar.low
    if candle_range <= 0 or bar.close <= bar.open:
        return False
    body = abs(bar.close - bar.open)
    lower_wick = min(bar.open, bar.close) - bar.low
    return body / candle_range >= 0.40 and (lower_wick >= body or isclose(lower_wick, body, rel_tol=1e-9, abs_tol=1e-12))


def _is_bearish_pin(bar: ResearchBar) -> bool:
    candle_range = bar.high - bar.low
    if candle_range <= 0 or bar.close >= bar.open:
        return False
    body = abs(bar.close - bar.open)
    upper_wick = bar.high - max(bar.open, bar.close)
    return body / candle_range >= 0.40 and (upper_wick >= body or isclose(upper_wick, body, rel_tol=1e-9, abs_tol=1e-12))


def _is_bullish_engulfing(previous: ResearchBar, current: ResearchBar) -> bool:
    return (
        previous.close < previous.open
        and current.close > current.open
        and current.open <= previous.close
        and current.close >= previous.open
    )


def _is_bearish_engulfing(previous: ResearchBar, current: ResearchBar) -> bool:
    return (
        previous.close > previous.open
        and current.close < current.open
        and current.open >= previous.close
        and current.close <= previous.open
    )


def _confirmation(bars: Sequence[ResearchBar], index: int, direction: Direction) -> Optional[str]:
    current = bars[index]
    previous = bars[index - 1] if index > 0 else None
    if direction is Direction.BUY:
        if _is_bullish_pin(current):
            return "Pin Bar"
        if previous is not None and _is_bullish_engulfing(previous, current):
            return "Engulfing"
    else:
        if _is_bearish_pin(current):
            return "Pin Bar"
        if previous is not None and _is_bearish_engulfing(previous, current):
            return "Engulfing"
    return None


def detect_breakout_retest(
    bars: Sequence[ResearchBar],
    pip_size: float,
    config: BreakoutRetestConfig = BreakoutRetestConfig(),
    *,
    min_signal_index: int = 0,
) -> tuple[BreakoutRetestSignal, ...]:
    """Detect completed Breakout + Retest setups without look-ahead bias.

    ``min_signal_index`` defines an evaluation boundary. Bars before the boundary
    remain available as historical context for consolidation and volume baselines,
    but a confirmation before that boundary can never become a returned signal.
    This is the key distinction between warm-up context and OOS performance data.
    """
    config.validate()
    if not isfinite(float(pip_size)) or pip_size <= 0:
        raise ValueError("pip_size must be finite and positive")
    if type(min_signal_index) is not int or min_signal_index < 0 or min_signal_index > len(bars):
        raise ValueError("min_signal_index must be an integer within bars")
    if len(bars) < config.consolidation_bars + config.volume_lookback + 2:
        return ()
    for bar in bars:
        bar.validate()

    signals: list[BreakoutRetestSignal] = []
    used_breakouts: set[int] = set()
    first_breakout = config.volume_lookback + config.consolidation_bars
    for breakout_index in range(first_breakout, len(bars) - 1):
        if breakout_index in used_breakouts:
            continue
        consolidation = bars[breakout_index - config.consolidation_bars : breakout_index]
        range_high = max(bar.high for bar in consolidation)
        range_low = min(bar.low for bar in consolidation)
        range_pips = (range_high - range_low) / pip_size
        if not config.min_range_pips <= range_pips <= config.max_range_pips:
            continue

        breakout = bars[breakout_index]
        body_pct = _body_pct(breakout)
        average_volume = sum(
            bar.volume for bar in bars[breakout_index - config.volume_lookback : breakout_index]
        ) / config.volume_lookback
        volume_ratio = breakout.volume / average_volume if average_volume > 0 else 0.0
        if body_pct <= config.breakout_body_pct or volume_ratio <= config.volume_multiplier:
            continue

        if breakout.close > range_high:
            direction = Direction.BUY
            level = range_high
        elif breakout.close < range_low:
            direction = Direction.SELL
            level = range_low
        else:
            continue

        last_retest = min(len(bars), breakout_index + 1 + config.retest_max_bars)
        for index in range(breakout_index + 1, last_retest):
            retest = bars[index]
            touched = retest.low <= level <= retest.high
            if not touched:
                continue
            confirmation = _confirmation(bars, index, direction)
            if confirmation is None or index < min_signal_index:
                continue
            entry = retest.close
            if direction is Direction.BUY:
                sl = min(retest.low, level) - config.sl_buffer_pips * pip_size
                risk = entry - sl
                if risk <= 0:
                    continue
                tp1, tp2, tp3 = (
                    entry + risk * config.tp1_rr,
                    entry + risk * config.tp2_rr,
                    entry + risk * config.tp3_rr,
                )
            else:
                sl = max(retest.high, level) + config.sl_buffer_pips * pip_size
                risk = sl - entry
                if risk <= 0:
                    continue
                tp1, tp2, tp3 = (
                    entry - risk * config.tp1_rr,
                    entry - risk * config.tp2_rr,
                    entry - risk * config.tp3_rr,
                )

            signals.append(
                BreakoutRetestSignal(
                    direction=direction,
                    signal_time=retest.timestamp,
                    breakout_time=breakout.timestamp,
                    breakout_level=level,
                    entry_price=entry,
                    sl_price=sl,
                    tp1=tp1,
                    tp2=tp2,
                    tp3=tp3,
                    body_pct=body_pct,
                    volume_ratio=volume_ratio,
                    confirmation=confirmation,
                )
            )
            used_breakouts.add(breakout_index)
            break

    return tuple(signals)
