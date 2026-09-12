"""Causal entry models for SHREEK V5.1.

The module is analysis-only: it produces TradeSignal objects and never sends
orders. All calculations operate on the supplied closed-bar data. A signal is
not a trade; downstream scoring and risk gates must admit it before execution.
"""
from __future__ import annotations

from math import isfinite
from typing import Optional, Sequence

import pandas as pd

from config.settings import Settings
from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import FairValueGap, MarketStructure, OrderBlock, TradeSignal
from market.fvg import find_fvgs, nearest_fvg
from market.liquidity import detect_liquidity_sweep
from market.order_blocks import find_order_block
from market.structure import determine_structure


def _last_float(df: pd.DataFrame, column: str) -> Optional[float]:
    if column not in df.columns or df.empty:
        return None
    try:
        value = float(df.iloc[-1][column])
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _directional_candle(df: pd.DataFrame, direction: Direction) -> bool:
    if df.empty or not {"open", "close"}.issubset(df.columns):
        return False
    try:
        o = float(df.iloc[-1]["open"])
        c = float(df.iloc[-1]["close"])
    except (TypeError, ValueError):
        return False
    return c > o if direction == Direction.BUY else c < o


def _matching_event(structure: MarketStructure, direction: Direction) -> bool:
    if direction == Direction.BUY:
        return structure.event.value in {"BOS_BULLISH", "CHOCH_BULLISH"}
    if direction == Direction.SELL:
        return structure.event.value in {"BOS_BEARISH", "CHOCH_BEARISH"}
    return False


def _stop_from_zone(
    direction: Direction,
    entry: float,
    ob: Optional[OrderBlock],
    fvg: Optional[FairValueGap],
    structure: MarketStructure,
    atr: float,
) -> Optional[float]:
    candidates: list[float] = []
    if direction == Direction.BUY:
        if ob is not None:
            candidates.append(float(ob.low))
        if fvg is not None:
            candidates.append(float(fvg.bottom))
        if structure.last_swing_low is not None:
            candidates.append(float(structure.last_swing_low))
        candidates.append(entry - max(atr * 0.5, 1e-12))
        below = [x for x in candidates if isfinite(x) and 0 < x < entry]
        return min(below) if below else None
    if direction == Direction.SELL:
        if ob is not None:
            candidates.append(float(ob.high))
        if fvg is not None:
            candidates.append(float(fvg.top))
        if structure.last_swing_high is not None:
            candidates.append(float(structure.last_swing_high))
        candidates.append(entry + max(atr * 0.5, 1e-12))
        above = [x for x in candidates if isfinite(x) and x > entry]
        return max(above) if above else None
    return None


def detect_fvg_failure(
    df: pd.DataFrame,
    fvg: Optional[FairValueGap],
    direction: Direction,
    lookback: int = 5,
) -> bool:
    """Return True when price trades through an FVG and closes back against it."""
    if fvg is None or direction not in (Direction.BUY, Direction.SELL):
        return False
    if df.empty or not {"high", "low", "close"}.issubset(df.columns):
        return False
    window = df.tail(max(1, int(lookback)))
    for _, row in window.iterrows():
        try:
            high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        except (TypeError, ValueError):
            continue
        if direction == Direction.BUY and low <= float(fvg.bottom) and close > float(fvg.top):
            return True
        if direction == Direction.SELL and high >= float(fvg.top) and close < float(fvg.bottom):
            return True
    return False


def analyze_m15_entry_signal(
    df_m15: pd.DataFrame,
    trade_direction: Direction,
    settings: Settings,
) -> TradeSignal:
    """Build an M15 entry signal from confirmed structure, liquidity and setup evidence."""
    frame = Timeframe.M15
    empty = TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, 0.0, 0.0, 0.0, "")
    if trade_direction not in (Direction.BUY, Direction.SELL) or df_m15 is None or df_m15.empty:
        return empty
    price = _last_float(df_m15, "close")
    atr = _last_float(df_m15, "atr")
    if price is None or atr is None or atr <= 0:
        return empty

    structure = determine_structure(
        df_m15, frame, atr=atr,
        threshold_atr=settings.bos_break_threshold_atr,
        confirmation_bars=settings.swing_window.get("M15", 10),
    )
    bos_confirmed = _matching_event(structure, trade_direction)
    if settings.m15_bos_required and not bos_confirmed:
        return TradeSignal(SignalStatus.WAIT, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "M15 structure confirmation pending", bos_confirmed=False, structure=structure)

    ob = find_order_block(df_m15, trade_direction, price, structure.last_swing_high, structure.last_swing_low, settings.ob_min_body_atr)
    fvgs = find_fvgs(df_m15, lookback=min(40, settings.fvg_max_age_bars))
    fvg = nearest_fvg(fvgs, price, trade_direction)
    sweep = detect_liquidity_sweep(df_m15, structure)
    sweep_confirmed = sweep.swept_low if trade_direction == Direction.BUY else sweep.swept_high
    candle_confirmed = _directional_candle(df_m15, trade_direction)

    if settings.m15_sweep_confirmation and not sweep_confirmed:
        return TradeSignal(SignalStatus.WAIT, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "Liquidity sweep confirmation pending", candle_confirmation=candle_confirmed, bos_confirmed=bos_confirmed, sweep_confirmed=False, structure=structure)
    if settings.m15_candle_confirmation and not candle_confirmed:
        return TradeSignal(SignalStatus.WAIT, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "M15 candle confirmation pending", candle_confirmation=False, bos_confirmed=bos_confirmed, sweep_confirmed=sweep_confirmed, structure=structure)

    combined = ob is not None and fvg is not None and not (float(ob.high) < float(fvg.bottom) or float(fvg.top) < float(ob.low))
    fvg_failure = settings.m15_fvg_entry and detect_fvg_failure(df_m15, fvg, trade_direction)
    if combined:
        setup, confidence = SetupType.COMBINED, 0.95
    elif ob is not None and settings.m15_ob_entry:
        setup, confidence = SetupType.OB_ENTRY, 0.85
    elif fvg is not None and settings.m15_fvg_entry:
        setup, confidence = SetupType.FVG_ENTRY, 0.80
    elif sweep_confirmed:
        setup, confidence = SetupType.SWEEP_ENTRY, 0.70
    else:
        return TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "No executable M15 setup", candle_confirmation=candle_confirmed, bos_confirmed=bos_confirmed, sweep_confirmed=sweep_confirmed, structure=structure)

    confidence += 0.05
    if sweep_confirmed:
        confidence += 0.05
    if fvg_failure:
        setup = SetupType.FVG_FAILURE
        confidence = min(0.99, confidence + 0.05)
    sl = _stop_from_zone(trade_direction, price, ob, fvg, structure, atr)
    if sl is None:
        return TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "Unable to construct protective stop", structure=structure)
    return TradeSignal(
        SignalStatus.VALID, setup, frame, trade_direction, price, sl,
        min(0.99, confidence),
        "M15 causal entry: structure + liquidity + OB/FVG; downstream risk gate required",
        candle_confirmation=candle_confirmed,
        bos_confirmed=bos_confirmed,
        sweep_confirmed=sweep_confirmed,
        fvg_failure=fvg_failure,
        order_block=ob, fvg=fvg, structure=structure,
    )


def analyze_execution_frame(
    df: pd.DataFrame,
    trade_direction: Direction,
    frame: Timeframe,
    settings: Settings,
) -> TradeSignal:
    """Analyze M15/M5/M3 execution evidence without using future bars."""
    if frame not in (Timeframe.M15, Timeframe.M5, Timeframe.M3):
        return TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, 0.0, 0.0, 0.0, "Unsupported execution frame")
    if df is None or df.empty or trade_direction not in (Direction.BUY, Direction.SELL):
        return TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, 0.0, 0.0, 0.0, "Invalid execution data")
    price, atr = _last_float(df, "close"), _last_float(df, "atr")
    if price is None or atr is None or atr <= 0:
        return TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, 0.0, 0.0, 0.0, "Invalid execution price/ATR")
    window = settings.swing_window.get(frame.value, 12)
    structure = determine_structure(df, frame, atr=atr, threshold_atr=settings.bos_break_threshold_atr, confirmation_bars=window)
    ob = find_order_block(df, trade_direction, price, structure.last_swing_high, structure.last_swing_low, settings.ob_min_body_atr)
    fvg = nearest_fvg(find_fvgs(df, lookback=min(40, settings.fvg_max_age_bars)), price, trade_direction)
    sweep = detect_liquidity_sweep(df, structure)
    sweep_confirmed = sweep.swept_low if trade_direction == Direction.BUY else sweep.swept_high
    candle = _directional_candle(df, trade_direction)
    failure = detect_fvg_failure(df, fvg, trade_direction)
    if frame == Timeframe.M3 and settings.m3_fvg_failure_required and not failure:
        return TradeSignal(SignalStatus.WAIT, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "M3 FVG-failure confirmation pending", candle_confirmation=candle, bos_confirmed=_matching_event(structure, trade_direction), sweep_confirmed=sweep_confirmed, fvg_failure=False, structure=structure)
    combined = ob is not None and fvg is not None and not (float(ob.high) < float(fvg.bottom) or float(fvg.top) < float(ob.low))

    if failure and frame == Timeframe.M3:
        setup, confidence = SetupType.FVG_FAILURE, 0.95
    elif combined:
        setup, confidence = SetupType.COMBINED, 0.90
    elif ob is not None:
        setup, confidence = SetupType.OB_ENTRY, 0.85
    elif fvg is not None:
        setup, confidence = SetupType.FVG_ENTRY, 0.75
    elif sweep_confirmed:
        setup, confidence = SetupType.SWEEP_ENTRY, 0.65
    else:
        return TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "No execution setup", structure=structure)
    if candle:
        confidence += 0.05
    if sweep_confirmed:
        confidence += 0.05
    sl = _stop_from_zone(trade_direction, price, ob, fvg, structure, atr)
    if sl is None:
        return TradeSignal(SignalStatus.NO_SIGNAL, SetupType.NONE, frame, trade_direction, price, 0.0, 0.0, "No valid protective stop", structure=structure)
    return TradeSignal(SignalStatus.VALID, setup, frame, trade_direction, price, sl, min(0.99, confidence), "Execution-frame confirmation; risk gate required", candle_confirmation=candle, bos_confirmed=_matching_event(structure, trade_direction), sweep_confirmed=sweep_confirmed, fvg_failure=failure, order_block=ob, fvg=fvg, structure=structure)


def select_best_execution_frame(signals: Sequence[TradeSignal]) -> Optional[TradeSignal]:
    """Select the strongest valid execution signal deterministically."""
    candidates = [s for s in signals if s is not None and s.is_valid and s.aligned]
    if not candidates:
        return None
    frame_bonus = {Timeframe.M3: 3, Timeframe.M5: 2, Timeframe.M15: 1}
    return max(candidates, key=lambda s: ((1000 if s.fvg_failure else 0) + s.confidence * 100 + frame_bonus.get(s.frame, 0)))
