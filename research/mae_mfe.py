"""Deterministic MAE/MFE analytics for SHREEK V5.2 research.

Research-only analytics: no order routing, broker access, or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from core.enums import Direction


@dataclass(frozen=True)
class TradeExcursion:
    entry: float
    exit: float
    mae: float
    mfe: float


def measure_excursion(
    direction: Direction,
    entry: float,
    exit: float,
    highs: Sequence[float],
    lows: Sequence[float],
) -> TradeExcursion:
    """Measure adverse/favorable price excursion in absolute price units."""
    values = [*highs, *lows]
    if not isfinite(entry) or not isfinite(exit) or not values:
        raise ValueError("entry, exit and excursion data are required")
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have equal length")
    if any(not isfinite(value) for value in values):
        raise ValueError("excursion data must be finite")
    if any(low > high for high, low in zip(highs, lows)):
        raise ValueError("low cannot exceed high")

    if direction is Direction.LONG:
        adverse = max(0.0, entry - min(lows))
        favorable = max(0.0, max(highs) - entry)
    elif direction is Direction.SHORT:
        adverse = max(0.0, max(highs) - entry)
        favorable = max(0.0, entry - min(lows))
    else:
        raise ValueError("unsupported direction")

    return TradeExcursion(entry=entry, exit=exit, mae=adverse, mfe=favorable)
