"""Liquidity sweep detection on a specific closed candle."""
from __future__ import annotations
import pandas as pd
from core.models import LiquiditySweep, MarketStructure


def _causal_frame(df: pd.DataFrame, as_of_index: int | None) -> pd.DataFrame:
    """Return only candles available at the requested closed-bar boundary."""
    if as_of_index is None:
        return df
    if isinstance(as_of_index, bool) or not isinstance(as_of_index, int) or as_of_index < 0:
        raise ValueError("as_of_index must be a non-negative integer")
    if as_of_index >= len(df):
        raise ValueError("as_of_index is outside the data frame")
    return df.iloc[:as_of_index + 1]


def detect_liquidity_sweep(
    df: pd.DataFrame,
    structure: MarketStructure,
    lookback: int = 15,
    as_of_index: int | None = None,
) -> LiquiditySweep:
    """Detect sweeps using only candles available at the evaluation boundary."""
    if structure.last_swing_high is None or structure.last_swing_low is None:
        return LiquiditySweep(swept_high=False, swept_low=False, details="")
    data = _causal_frame(df, as_of_index)
    s = data.iloc[-lookback:]
    if s.empty:
        return LiquiditySweep(swept_high=False, swept_low=False, details="")
    sh, sl = float(structure.last_swing_high), float(structure.last_swing_low)
    high_hits = s[(s["high"] > sh) & (s["close"] < sh)]
    low_hits = s[(s["low"] < sl) & (s["close"] > sl)]
    details = []
    if not high_hits.empty:
        x = high_hits.iloc[-1]
        details.append(f"High sweep: wick {x.high:.5f}, close {x.close:.5f}")
    if not low_hits.empty:
        x = low_hits.iloc[-1]
        details.append(f"Low sweep: wick {x.low:.5f}, close {x.close:.5f}")
    return LiquiditySweep(
        swept_high=not high_hits.empty,
        swept_low=not low_hits.empty,
        details=" | ".join(details) if details else "No sweep detected",
    )
