"""Causal structure-event rules for ICT/SMC style confirmation.

A structure event is only considered confirmed when the *closed* candle
closes beyond the prior confirmed swing by an ATR-scaled threshold.
This module intentionally does not manufacture a swing; callers provide the
previous confirmed swing levels.
"""
from __future__ import annotations
from dataclasses import dataclass
from core.enums import Direction, StructureEvent

@dataclass(frozen=True)
class StructureDecision:
    event: StructureEvent
    bias: Direction
    level: float | None
    displacement_atr: float


def classify_break(close: float, prev_swing_high: float | None, prev_swing_low: float | None,
                   atr: float, threshold_atr: float, prior_bias: Direction) -> StructureDecision:
    if atr <= 0 or threshold_atr < 0:
        return StructureDecision(StructureEvent.NONE, prior_bias, None, 0.0)
    threshold = atr * threshold_atr
    if prev_swing_high is not None and close > prev_swing_high + threshold:
        displacement = (close - prev_swing_high) / atr
        event = StructureEvent.BOS_BULLISH if prior_bias in (Direction.BUY, Direction.RANGE, Direction.UNKNOWN) else StructureEvent.CHOCH_BULLISH
        return StructureDecision(event, Direction.BUY, prev_swing_high, displacement)
    if prev_swing_low is not None and close < prev_swing_low - threshold:
        displacement = (prev_swing_low - close) / atr
        event = StructureEvent.BOS_BEARISH if prior_bias in (Direction.SELL, Direction.RANGE, Direction.UNKNOWN) else StructureEvent.CHOCH_BEARISH
        return StructureDecision(event, Direction.SELL, prev_swing_low, displacement)
    return StructureDecision(StructureEvent.NONE, prior_bias, None, 0.0)
