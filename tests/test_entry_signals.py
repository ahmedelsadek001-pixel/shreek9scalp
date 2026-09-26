import pandas as pd

from config.settings import SETTINGS
from core.enums import Direction, SignalStatus, Timeframe
from market.entry_signals import analyze_execution_frame, select_best_execution_frame


def _df(n=80):
    rows=[]
    price=2000.0
    for i in range(n):
        if i % 12 == 0:
            price += 3
        elif i % 12 == 6:
            price -= 2
        rows.append({"open":price,"high":price+1.5,"low":price-1.5,"close":price+0.5,"atr":2.0})
        price += 0.1
    return pd.DataFrame(rows)


def test_invalid_direction_fails_closed():
    signal = analyze_execution_frame(_df(), Direction.UNKNOWN, Timeframe.M5, SETTINGS)
    assert signal.status == SignalStatus.NO_SIGNAL
    assert not signal.is_valid


def test_invalid_execution_frame_fails_closed():
    signal = analyze_execution_frame(_df(), Direction.BUY, Timeframe.H1, SETTINGS)
    assert signal.status == SignalStatus.NO_SIGNAL


def test_selection_requires_valid_signals():
    a = analyze_execution_frame(_df(), Direction.UNKNOWN, Timeframe.M5, SETTINGS)
    assert select_best_execution_frame([a]) is None


def test_missing_atr_fails_closed():
    df = _df().drop(columns=["atr"])
    signal = analyze_execution_frame(df, Direction.BUY, Timeframe.M5, SETTINGS)
    assert signal.status == SignalStatus.NO_SIGNAL


def _signal_signature(signal):
    return (
        signal.status,
        signal.setup_type,
        signal.frame,
        signal.direction,
        signal.entry_price,
        signal.sl_price,
        signal.confidence,
        signal.candle_confirmation,
        signal.bos_confirmed,
        signal.sweep_confirmed,
        signal.fvg_failure,
        signal.order_block,
        signal.fvg,
        signal.structure,
    )


def test_execution_signal_as_of_boundary_ignores_future_mutation():
    df = _df()
    mutated = df.copy()
    mutated.loc[60:, ["high", "low", "close"]] = [[10000, 1000, 9000]] * (len(df) - 60)
    a = analyze_execution_frame(df, Direction.BUY, Timeframe.M5, SETTINGS, as_of_index=59)
    b = analyze_execution_frame(mutated, Direction.BUY, Timeframe.M5, SETTINGS, as_of_index=59)
    assert _signal_signature(a) == _signal_signature(b)


def test_execution_signal_rejects_invalid_causal_boundary():
    df = _df()
    signal = analyze_execution_frame(df, Direction.BUY, Timeframe.M5, SETTINGS, as_of_index=len(df))
    assert signal.status == SignalStatus.NO_SIGNAL
    assert not signal.is_valid
