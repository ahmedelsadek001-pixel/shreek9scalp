import pandas as pd
import pytest

from core.enums import Direction, Timeframe
from market.fvg import find_fvgs
from market.liquidity import detect_liquidity_sweep
from market.order_blocks import find_all_order_blocks
from market.structure import determine_structure


def _bars():
    return pd.DataFrame([
        {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "atr": 2.0, "avg_body": 1.0},
        {"open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "atr": 2.0, "avg_body": 1.0},
        {"open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0, "atr": 2.0, "avg_body": 1.0},
        {"open": 103.0, "high": 103.5, "low": 100.0, "close": 100.5, "atr": 2.0, "avg_body": 1.0},
        {"open": 100.5, "high": 106.0, "low": 100.0, "close": 105.0, "atr": 2.0, "avg_body": 1.0},
        {"open": 105.0, "high": 107.0, "low": 104.0, "close": 106.0, "atr": 2.0, "avg_body": 1.0},
        {"open": 106.0, "high": 108.0, "low": 105.0, "close": 107.0, "atr": 2.0, "avg_body": 1.0},
        {"open": 107.0, "high": 109.0, "low": 106.0, "close": 108.0, "atr": 2.0, "avg_body": 1.0},
    ])


def _signature(items):
    return [tuple(vars(item).values()) for item in items]


def test_structure_as_of_boundary_ignores_future_mutation():
    df = _bars()
    mutated = df.copy()
    mutated.loc[6:, ["high", "low", "close"]] = [[1000, 500, 900], [1200, 400, 1100]]
    a = determine_structure(df, Timeframe.M15, atr=2.0, confirmation_bars=2, as_of_index=5)
    b = determine_structure(mutated, Timeframe.M15, atr=2.0, confirmation_bars=2, as_of_index=5)
    assert a == b


def test_fvg_as_of_boundary_ignores_future_mutation():
    df = _bars()
    mutated = df.copy()
    mutated.loc[6:, ["high", "low"]] = [[1000, 500], [1200, 400]]
    a = _signature(find_fvgs(df, lookback=40, as_of_index=5))
    b = _signature(find_fvgs(mutated, lookback=40, as_of_index=5))
    assert a == b


def test_order_blocks_as_of_boundary_ignores_future_mutation():
    df = _bars()
    mutated = df.copy()
    mutated.loc[6:, ["high", "low", "close"]] = [[1000, 500, 900], [1200, 400, 1100]]
    a = _signature(find_all_order_blocks(df, Direction.BUY, 0.5, as_of_index=5))
    b = _signature(find_all_order_blocks(mutated, Direction.BUY, 0.5, as_of_index=5))
    assert a == b


def test_liquidity_as_of_boundary_ignores_future_mutation():
    df = _bars()
    mutated = df.copy()
    mutated.loc[6:, ["high", "low", "close"]] = [[1000, 500, 900], [1200, 400, 1100]]
    structure = determine_structure(df, Timeframe.M15, atr=2.0, confirmation_bars=2, as_of_index=5)
    a = detect_liquidity_sweep(df, structure, as_of_index=5)
    b = detect_liquidity_sweep(mutated, structure, as_of_index=5)
    assert a == b


def test_causal_boundaries_fail_closed():
    df = _bars()
    with pytest.raises(ValueError):
        find_fvgs(df, as_of_index=True)
    with pytest.raises(ValueError):
        find_all_order_blocks(df, Direction.BUY, 0.5, as_of_index=len(df))
    with pytest.raises(ValueError):
        determine_structure(df, as_of_index=-1)
    with pytest.raises(ValueError):
        detect_liquidity_sweep(df, determine_structure(df, as_of_index=5), as_of_index=len(df))
