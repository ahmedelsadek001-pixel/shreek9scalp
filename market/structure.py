"""Causal market-structure helpers for V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.enums import Direction, StructureEvent, Timeframe
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


def _timeframe(value: str | Timeframe) -> Optional[Timeframe]:
    if isinstance(value, Timeframe):
        return value
    try:
        return Timeframe(str(value).upper())
    except (TypeError, ValueError):
        return None


def confirmed_swings(df: pd.DataFrame, confirmation_bars: int = 2) -> list[SwingPoint]:
    """Return swings only after the required right-side candles have closed."""
    if not _valid(df) or confirmation_bars < 1:
        return []
    values = df.reset_index(drop=True)
    out: list[SwingPoint] = []
    for i in range(confirmation_bars, len(values) - confirmation_bars):
        right = values.iloc[i + 1:i + 1 + confirmation_bars]
        left = values.iloc[max(0, i - confirmation_bars):i]
        high = float(values.iloc[i]["high"])
        low = float(values.iloc[i]["low"])
        if high >= float(left["high"].max()) and high >= float(right["high"].max()):
            out.append(SwingPoint(i, high, "high", i + confirmation_bars))
        if low <= float(left["low"].min()) and low <= float(right["low"].min()):
            out.append(SwingPoint(i, low, "low", i + confirmation_bars))
    return out


def determine_structure(
    df: pd.DataFrame,
    timeframe: str | Timeframe = Timeframe.M15,
    prior_bias: Direction = Direction.UNKNOWN,
    atr: Optional[float] = None,
    threshold_atr: float = 0.10,
    confirmation_bars: int = 2,
) -> MarketStructure:
    """Classify the latest closed candle against confirmed swings.

    Invalid timeframe input is rejected instead of silently becoming M15; this
    prevents a configuration/data-integrity error from changing strategy logic.
    """
    tf = _timeframe(timeframe)
    if tf is None:
        return MarketStructure(Timeframe.M15, Direction.UNKNOWN, StructureEvent.NONE, None, None, True)
    if not _valid(df):
        return MarketStructure(tf, Direction.UNKNOWN, StructureEvent.NONE, None, None, True)
    data = df.reset_index(drop=True)
    swings = confirmed_swings(data, confirmation_bars)
    if not swings:
        return MarketStructure(tf, prior_bias, StructureEvent.NONE, None, None, True)

    usable = [s for s in swings if s.confirmed_at < len(data)]
    highs = [s for s in usable if s.kind == "high"]
    lows = [s for s in usable if s.kind == "low"]
    last_high = highs[-1].price if highs else None
    last_low = lows[-1].price if lows else None

    if atr is None or atr <= 0:
        if "atr" in data.columns and pd.notna(data["atr"].iloc[-1]) and data["atr"].iloc[-1] > 0:
            atr = float(data["atr"].iloc[-1])
        else:
            tr = pd.concat([
                data["high"] - data["low"],
                (data["high"] - data["close"].shift()).abs(),
                (data["low"] - data["close"].shift()).abs(),
            ], axis=1).max(axis=1)
            atr = float(tr.tail(14).mean()) if not tr.empty else 0.0

    decision = classify_break(
        float(data.iloc[-1]["close"]), last_high, last_low,
        float(atr), threshold_atr, prior_bias,
    )
    return MarketStructure(
        timeframe=tf,
        bias=decision.bias,
        event=decision.event,
        last_swing_high=last_high,
        last_swing_low=last_low,
        is_ranging=decision.event == StructureEvent.NONE,
    )
