"""Deterministic execution-level construction for SHREEK V5.1.

This module calculates levels only. It never sends orders and fails closed on
invalid prices or insufficient reward/risk.
"""
from __future__ import annotations

from math import isfinite
from typing import Optional

from core.enums import Direction
from core.models import ExecutionLevels, TradeSignal


def build_execution_levels(
    signal: TradeSignal,
    draw_target: Optional[float] = None,
    min_rr: float = 1.5,
    atr_sl_buffer: float = 0.0,
) -> Optional[ExecutionLevels]:
    """Build TP1/TP2/TP3 from a validated signal.

    TP1 is 1R. TP2 uses the supplied draw target when it provides at least
    ``min_rr``. Otherwise TP2 is the minimum acceptable reward target,
    ``min_rr * R``. TP3 is 1.5x the TP2 distance. Invalid or non-finite
    inputs return None.
    """
    if signal is None or signal.direction not in (Direction.BUY, Direction.SELL):
        return None
    entry = float(signal.entry_price)
    sl = float(signal.sl_price)
    if not all(isfinite(x) and x > 0 for x in (entry, sl)):
        return None
    if min_rr <= 0 or not isfinite(min_rr) or atr_sl_buffer < 0 or not isfinite(atr_sl_buffer):
        return None

    if signal.direction == Direction.BUY and sl >= entry:
        return None
    if signal.direction == Direction.SELL and sl <= entry:
        return None

    risk = abs(entry - sl)
    if atr_sl_buffer:
        # Buffer is applied away from entry, never toward it.
        sl = sl - atr_sl_buffer if signal.direction == Direction.BUY else sl + atr_sl_buffer
        if sl <= 0 or (signal.direction == Direction.BUY and sl >= entry) or (signal.direction == Direction.SELL and sl <= entry):
            return None
        risk = abs(entry - sl)
    if risk <= 0 or not isfinite(risk):
        return None

    direction_sign = 1.0 if signal.direction == Direction.BUY else -1.0
    tp1 = entry + direction_sign * risk
    fallback_tp2 = entry + direction_sign * min_rr * risk
    tp2 = fallback_tp2

    if draw_target is not None and isfinite(float(draw_target)):
        target = float(draw_target)
        target_rr = abs(target - entry) / risk
        direction_ok = target > entry if signal.direction == Direction.BUY else target < entry
        if direction_ok and target_rr >= min_rr:
            tp2 = target

    tp3_distance = abs(tp2 - entry) * 1.5
    tp3 = entry + direction_sign * tp3_distance
    rr1 = abs(tp1 - entry) / risk

    return ExecutionLevels(
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        risk=risk,
        rr1=rr1,
        setup_type=signal.setup_type,
        confidence=signal.confidence,
        selected_frame=signal.frame,
        details="Deterministic R-based levels; no order execution performed",
    )
