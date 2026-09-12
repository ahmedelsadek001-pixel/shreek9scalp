from datetime import datetime

import pytest

from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.execution_levels import build_execution_levels
from core.models import TradeSignal
from core.position_lifecycle import (
    LifecyclePolicy,
    after_tp1,
    after_tp2,
    initial_state,
    tp1_action,
    tp2_action,
    tp3_action,
)


def make_levels(direction: Direction):
    signal = TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.OB_ENTRY,
        frame=Timeframe.M5,
        direction=direction,
        entry_price=100.0,
        sl_price=99.0 if direction == Direction.BUY else 101.0,
    )
    return build_execution_levels(signal, min_rr=2.0)


def test_default_lifecycle_closes_50_25_25():
    levels = make_levels(Direction.BUY)
    policy = LifecyclePolicy()
    state = initial_state(1.0, levels, policy)
    a1 = tp1_action(state, 1.0, levels, policy)
    assert a1.volume == pytest.approx(0.5)
    state = after_tp1(state, levels, policy, 1.0)
    assert state.remaining_volume == pytest.approx(0.5)
    a2 = tp2_action(state, 1.0, levels, policy)
    assert a2.volume == pytest.approx(0.25)
    state = after_tp2(state, 1.0, levels, policy)
    assert state.remaining_volume == pytest.approx(0.25)
    a3 = tp3_action(state, levels)
    assert a3.volume == pytest.approx(0.25)


def test_buy_breakeven_moves_stop_to_entry():
    levels = make_levels(Direction.BUY)
    state = initial_state(1.0, levels)
    state = after_tp1(state, levels, LifecyclePolicy(), 1.0)
    assert state.breakeven_active is True
    assert state.stop_price == pytest.approx(levels.entry)


def test_sell_breakeven_moves_stop_to_entry():
    levels = make_levels(Direction.SELL)
    state = initial_state(1.0, levels)
    state = after_tp1(state, levels, LifecyclePolicy(), 1.0)
    assert state.breakeven_active is True
    assert state.stop_price == pytest.approx(levels.entry)


def test_tp_order_is_enforced():
    levels = make_levels(Direction.BUY)
    state = initial_state(1.0, levels)
    with pytest.raises(ValueError, match="TP1"):
        tp2_action(state, 1.0, levels, LifecyclePolicy())
    with pytest.raises(ValueError, match="TP2"):
        tp3_action(state, levels)


def test_policy_fractions_must_sum_to_one():
    levels = make_levels(Direction.BUY)
    policy = LifecyclePolicy(tp1_fraction=0.6, tp2_fraction=0.2, tp3_fraction=0.1)
    with pytest.raises(ValueError, match="sum to 1"):
        initial_state(1.0, levels, policy)
