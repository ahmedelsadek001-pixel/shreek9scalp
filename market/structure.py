"""Causal market-structure helpers for V5.1.

The module intentionally avoids centered/forward-looking pivots at the
signal timestamp. A swing becomes usable only after ``confirmation_bars``
have closed to its right.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.enums import Direction, StructureEvent
from core.models import MarketStructure
from core.structure_rules import classify_break


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    kind: str
    confirmed_at: int


def _valid(df: pd.DataFrame) -> bool:
    return not df.empty and all(c in df.columns for c in ("high", "low", "close"))


def confirmed_swings(df: pd.DataFrame, confirmation_bars: int = 2) -> list[SwingPoint]:
    """Return confirmed local swings without using bars after confirmation.

    A high/low at i is confirmed at i+confirmation_bars when it remains the
    extreme versus that many subsequent *closed* candles. The returned
    ``confirmed_at`` is the first timestamp/index at which the swing is usable.
    """
    if not _valid(df) or confirmation_bars < 1:
        return []
    values = df.reset_index(drop=True)
    out: list[SwingPoint] = []
    for i in range(confirmation_bars, len(values) - confirmation_bars):
        right = values.iloc[i + 1 : i + 1 + confirmation_bars]
        left = values.iloc[max(0, i - confirmation_bars) : i]
        high = float(values.iloc[i]["high"])
        low = float(values.iloc[i]["low"])
        if high >= float(left["high"].max()) and high >= float(right["high"].max()):
            out.append(SwingPoint(i, high, "high", i + confirmation_bars))
        if low <= float(left["low"].min()) and low <= float(right["low"].min()):
            out.append(SwingPoint(i, low, "low", i + confirmation_bars))
    return out


def determine_structure(
    df: pd.DataFrame,
    timeframe: str = "M15",
    prior_bias: Direction = Direction.UNKNOWN,
    atr: Optional[float] = None,
    threshold_atr: float = 0.10,
    confirmation_bars: int = 2,
) -> MarketStructure:
    """Classify the latest closed candle against the latest confirmed swings."""
    if not _valid(df):
        return MarketStructure(timeframe, Direction.UNKNOWN, StructureEvent.NONE, None, None, True)
    data = df.reset_index(drop=True)
    swings = confirmed_swings(data, confirmation_bars)
    if not swings:
        return MarketStructure(timeframe, prior_bias, StructureEvent.NONE, None, None, True)

    usable = [s for s in swings if s.confirmed_at < len(data)]
    highs = [s for s in usable if s.kind == "high"]
    lows = [s for s in usable if s.kind == "low"]
    last_high = highs[-1].price if highs else None
    last_low = lows[-1].price if lows else None

    if atr is None or atr <= 0:
        rng = (data["high"] - data["low"]).tail(min(14, len(data)))
        atr = float(rng.mean()) if not rng.empty else 0.0

    decision = classify_break(
        float(data.iloc[-1]["close"]),
        last_high,
        last_low,
        float(atr),
        threshold_atr,
        prior_bias,
    )
    return MarketStructure(
        timeframe=timeframe,
        bias=decision.bias,
        event=decision.event,
        last_swing_high=last_high,
        last_swing_low=last_low,
        is_ranging=decision.event == StructureEvent.NONE,
    )
