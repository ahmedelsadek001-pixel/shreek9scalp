"""Order-block detection for closed-candle V5.1 analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd

from config.constants import OB_DISPLACEMENT_LOOKAHEAD_BARS, OB_MIN_BODY_VS_AVG_RATIO
from core.enums import Direction
from core.models import OrderBlock


def _is_valid_ob(body: float, avg_body: float, atr: float, ob_min_body_atr: float) -> bool:
    if not np.isfinite(body) or body <= 0:
        return False
    if atr <= 0 or body < ob_min_body_atr * atr:
        return False
    if avg_body > 0 and body < OB_MIN_BODY_VS_AVG_RATIO * avg_body:
        return False
    return True


def _causal_frame(df: pd.DataFrame, as_of_index: int | None) -> pd.DataFrame:
    """Return data available at the requested closed-bar boundary."""
    if as_of_index is None:
        return df
    if isinstance(as_of_index, bool) or not isinstance(as_of_index, int) or as_of_index < 0:
        raise ValueError("as_of_index must be a non-negative integer")
    if as_of_index >= len(df):
        raise ValueError("as_of_index is outside the data frame")
    return df.iloc[:as_of_index + 1]


def find_all_order_blocks(
    df: pd.DataFrame,
    direction: Direction,
    ob_min_body_atr: float,
    lookback: int = 40,
    as_of_index: int | None = None,
) -> list[OrderBlock]:
    """Find displacement-backed OBs using only candles available at evaluation time.

    The displacement look-ahead is confirmation data, not future data: a
    candidate is emitted only after the required confirmation candles exist.
    ``as_of_index`` makes that boundary explicit for historical research.
    """
    data = _causal_frame(df, as_of_index)
    required = {"open", "high", "low", "close"}
    if not required.issubset(data.columns) or len(data) < 5:
        return []
    subset = data.iloc[-lookback:].reset_index(drop=True)
    n = len(subset)
    if n < OB_DISPLACEMENT_LOOKAHEAD_BARS + 2:
        return []

    opens = subset["open"].to_numpy(dtype=float)
    highs = subset["high"].to_numpy(dtype=float)
    lows = subset["low"].to_numpy(dtype=float)
    closes = subset["close"].to_numpy(dtype=float)
    bodies = np.abs(closes - opens)
    atr = float(data["atr"].iloc[-1]) if "atr" in data.columns and pd.notna(data["atr"].iloc[-1]) else 0.0
    avg_body = float(data["avg_body"].iloc[-1]) if "avg_body" in data.columns and pd.notna(data["avg_body"].iloc[-1]) else 0.0
    valid_body = np.array([_is_valid_ob(b, avg_body, atr, ob_min_body_atr) for b in bodies])

    obs: list[OrderBlock] = []
    look = OB_DISPLACEMENT_LOOKAHEAD_BARS
    last_candidate = n - look - 1
    if direction == Direction.BUY:
        for i in range(last_candidate, 0, -1):
            if closes[i] >= opens[i] or not valid_body[i]:
                continue
            if np.max(highs[i + 1:i + 1 + look]) > highs[i]:
                obs.append(OrderBlock(float(highs[i]), float(lows[i]), i, float(bodies[i]), direction))
    elif direction == Direction.SELL:
        for i in range(last_candidate, 0, -1):
            if closes[i] <= opens[i] or not valid_body[i]:
                continue
            if np.min(lows[i + 1:i + 1 + look]) < lows[i]:
                obs.append(OrderBlock(float(highs[i]), float(lows[i]), i, float(bodies[i]), direction))
    return obs


def rank_order_blocks(
    obs: list[OrderBlock], current_price: float, direction: Direction,
    swing_high: float | None, swing_low: float | None,
) -> list[OrderBlock]:
    ranked: list[OrderBlock] = []
    for ob in obs:
        dist = abs(current_price - ob.mid)
        if direction == Direction.BUY and swing_low is not None:
            proximity = abs(ob.mid - swing_low)
        elif direction == Direction.SELL and swing_high is not None:
            proximity = abs(ob.mid - swing_high)
        else:
            proximity = float("inf")
        ranked.append(OrderBlock(ob.high, ob.low, ob.bar_index, ob.body_size, ob.direction, dist, proximity))
    ranked.sort(key=lambda o: (o.dist_to_price, o.proximity_to_swing, -o.body_size))
    return ranked


def find_order_block(
    df: pd.DataFrame, direction: Direction, current_price: float,
    swing_high: float | None, swing_low: float | None,
    ob_min_body_atr: float, lookback: int = 40,
    as_of_index: int | None = None,
) -> OrderBlock | None:
    obs = find_all_order_blocks(df, direction, ob_min_body_atr, lookback, as_of_index=as_of_index)
    if not obs:
        return None
    ranked = rank_order_blocks(obs, current_price, direction, swing_high, swing_low)
    return ranked[0] if ranked else None
