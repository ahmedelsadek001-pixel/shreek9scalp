"""Deterministic execution-level construction for SHREEK V5.1."""
from __future__ import annotations

from math import isfinite
from typing import Optional

from core.enums import Direction
from core.models import ExecutionLevels, TradeSignal


def build_execution_levels(
    signal: TradeSignal,
    draw_target: Optional[float] = None,
    min_rr: Optional[float] = None,
    atr_sl_buffer: float = 0.0,
) -> Optional[ExecutionLevels]:
    """Build TP1/TP2/TP3 without any broker or order side effects.

    TP1 is 1R. A directional draw target is accepted only when its RR meets
    ``min_rr``. If ``min_rr`` is omitted, the standalone API keeps its legacy
    2R fallback. The scanner passes its configured minimum explicitly.
    """
    if signal is None or signal.direction not in (Direction.BUY, Direction.SELL):
        return None
    try:
        entry = float(signal.entry_price)
        sl = float(signal.sl_price)
        rr_floor = 2.0 if min_rr is None else float(min_rr)
        buffer = float(atr_sl_buffer)
    except (TypeError, ValueError):
        return None
    if not all(isfinite(x) and x > 0 for x in (entry, sl)):
        return None
    if not isfinite(rr_floor) or rr_floor <= 0 or not isfinite(buffer) or buffer < 0:
        return None
    if signal.direction == Direction.BUY and sl >= entry:
        return None
    if signal.direction == Direction.SELL and sl <= entry:
        return None

    if buffer:
        sl = sl - buffer if signal.direction == Direction.BUY else sl + buffer
        if sl <= 0 or (signal.direction == Direction.BUY and sl >= entry) or (signal.direction == Direction.SELL and sl <= entry):
            return None

    risk = abs(entry - sl)
    if not isfinite(risk) or risk <= 0:
        return None
    sign = 1.0 if signal.direction == Direction.BUY else -1.0
    tp1 = entry + sign * risk
    tp2 = entry + sign * rr_floor * risk

    if draw_target is not None:
        try:
            target = float(draw_target)
        except (TypeError, ValueError):
            target = float("nan")
        if isfinite(target):
            directional = target > entry if signal.direction == Direction.BUY else target < entry
            target_rr = abs(target - entry) / risk
            if directional and target_rr >= rr_floor:
                tp2 = target

    tp3 = entry + sign * abs(tp2 - entry) * 1.5
    return ExecutionLevels(
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        risk=risk,
        rr1=1.0,
        setup_type=signal.setup_type,
        confidence=signal.confidence,
        selected_frame=signal.frame,
        details="Deterministic R-based levels; no order execution performed",
    )
