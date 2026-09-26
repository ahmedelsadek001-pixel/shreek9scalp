import pandas as pd

from core.enums import Direction, StructureEvent, Timeframe
from market.structure import confirmed_swings, determine_structure


def test_swing_is_not_usable_before_confirmation():
    df = pd.DataFrame({
        "high": [10, 12, 15, 13, 11, 10],
        "low": [8, 9, 10, 9, 8, 7],
        "close": [9, 11, 14, 12, 10, 8],
    })
    swings = confirmed_swings(df, confirmation_bars=2)
    high = next(s for s in swings if s.kind == "high")
    assert high.index == 2
    assert high.confirmed_at == 4


def test_structure_uses_typed_timeframe():
    df = pd.DataFrame({
        "high": [10, 12, 15, 13, 11, 16],
        "low": [8, 9, 10, 9, 8, 12],
        "close": [9, 11, 14, 12, 10, 16],
        "atr": [1.0] * 6,
    })
    result = determine_structure(df, "M15", Direction.UNKNOWN, atr=1.0, threshold_atr=0.1)
    assert result.timeframe == Timeframe.M15
    assert result.event in (StructureEvent.BOS_BULLISH, StructureEvent.NONE)
