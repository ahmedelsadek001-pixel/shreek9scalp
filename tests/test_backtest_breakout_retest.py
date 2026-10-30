from datetime import datetime, timedelta, timezone

import pytest

from core.enums import Direction, Timeframe
from research.backtest_breakout_retest import (
    BreakoutRetestBacktestConfig,
    build_breakout_retest_orders,
    run_breakout_retest_backtest,
    to_backtest_bars,
)
from research.breakout_retest import BreakoutRetestSignal, ResearchBar


def _bars() -> list[ResearchBar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        ResearchBar(start + timedelta(minutes=i), 100.003, 100.005, 100.002, 100.004, 100.0)
        for i in range(20)
    ]
    bars += [
        ResearchBar(start + timedelta(minutes=20 + i), 100.003, 100.005, 100.002, 100.004, 100.0)
        for i in range(6)
    ]
    bars.append(ResearchBar(start + timedelta(minutes=26), 100.003, 100.008, 100.0025, 100.0075, 200.0))
    bars.append(ResearchBar(start + timedelta(minutes=27), 100.0055, 100.0075, 100.004, 100.007, 100.0))
    bars.append(ResearchBar(start + timedelta(minutes=28), 100.007, 100.010, 100.006, 100.009, 100.0))
    return bars


def test_research_bars_convert_without_volume_leakage():
    bars = to_backtest_bars(_bars(), spread=0.0002)
    assert len(bars) == len(_bars())
    assert bars[-1].spread == pytest.approx(0.0002)
    assert not hasattr(bars[-1], "volume")


def test_breakout_retest_builds_causal_order():
    config = BreakoutRetestBacktestConfig(
        pip_size=0.0001,
        volume=0.03,
        point_value=1.0,
    )
    orders = build_breakout_retest_orders(_bars(), config)
    assert len(orders) == 1
    assert orders[0].direction is Direction.BUY
    assert orders[0].signal_time == datetime(2026, 1, 1, 0, 27, tzinfo=timezone.utc)


def test_orders_are_chronological_when_later_breakout_retests_first(monkeypatch):
    bars = _bars()

    def signal(signal_index, breakout_index, direction):
        entry = 100.0
        return BreakoutRetestSignal(
            direction=direction,
            signal_time=bars[signal_index].timestamp,
            breakout_time=bars[breakout_index].timestamp,
            breakout_level=entry,
            entry_price=entry,
            sl_price=99.0 if direction is Direction.BUY else 101.0,
            tp1=101.5 if direction is Direction.BUY else 98.5,
            tp2=102.5 if direction is Direction.BUY else 97.5,
            tp3=104.0 if direction is Direction.BUY else 96.0,
            body_pct=0.8,
            volume_ratio=2.0,
            confirmation="Pin Bar",
        )

    monkeypatch.setattr(
        "research.backtest_breakout_retest.detect_breakout_retest",
        lambda *_args, **_kwargs: (
            signal(28, 26, Direction.BUY),
            signal(27, 25, Direction.SELL),
        ),
    )

    orders = build_breakout_retest_orders(
        bars,
        BreakoutRetestBacktestConfig(pip_size=0.0001, point_value=1.0),
    )

    assert [order.signal_time for order in orders] == [
        bars[27].timestamp,
        bars[28].timestamp,
    ]


def test_breakout_retest_order_uses_configured_timeframe():
    config = BreakoutRetestBacktestConfig(
        pip_size=0.0001,
        timeframe=Timeframe.H1,
        point_value=1.0,
    )
    orders = build_breakout_retest_orders(_bars(), config)
    assert len(orders) == 1
    assert orders[0].levels.selected_frame is Timeframe.H1


def test_invalid_timeframe_is_rejected():
    config = BreakoutRetestBacktestConfig(
        pip_size=0.0001,
        timeframe="H1",
        point_value=1.0,
    )
    with pytest.raises(ValueError, match="timeframe"):
        build_breakout_retest_orders(_bars(), config)


def test_backtest_rejects_missing_point_value():
    config = BreakoutRetestBacktestConfig(pip_size=0.0001, volume=0.03)
    with pytest.raises(ValueError, match="point_value"):
        run_breakout_retest_backtest(_bars(), config)


def test_backtest_rejects_invalid_economics():
    with pytest.raises(ValueError, match="point_value"):
        run_breakout_retest_backtest(
            _bars(), BreakoutRetestBacktestConfig(pip_size=0.0001, point_value=0.0)
        )


def test_breakout_retest_runs_through_real_backtest_engine():
    result = run_breakout_retest_backtest(
        _bars(),
        BreakoutRetestBacktestConfig(pip_size=0.0001, volume=0.03, point_value=1.0),
    )

    assert result.stats.trades == 1
    assert result.trades[0].direction is Direction.BUY
    assert result.trades[0].tag == "breakout_retest"
    assert result.trades[0].exit_reason in {"TP", "SL", "EOD"}
    assert result.stats.ending_equity == pytest.approx(10000.0 + result.trades[0].net_pnl)


def test_negative_spread_is_rejected():
    with pytest.raises(ValueError):
        to_backtest_bars(_bars(), spread=-0.0001)
