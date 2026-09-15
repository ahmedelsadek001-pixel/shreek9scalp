from datetime import datetime, timedelta, timezone

import pytest

from core.enums import Direction, Timeframe
from research.backtest_breakout_retest import (
    BreakoutRetestBacktestConfig,
    build_breakout_retest_orders,
    run_breakout_retest_backtest,
    to_backtest_bars,
)
from research.breakout_retest import ResearchBar


def _bars() -> list[ResearchBar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(20):
        bars.append(ResearchBar(start + timedelta(minutes=i), 100.003, 100.005, 100.002, 100.004, 100.0))
    for i in range(6):
        bars.append(ResearchBar(start + timedelta(minutes=20 + i), 100.003, 100.005, 100.002, 100.004, 100.0))
    bars.append(ResearchBar(start + timedelta(minutes=26), 100.003, 100.008, 100.0025, 100.0075, 200.0))
    # Bullish pin-bar style retest: body is >= 40% of the range and the lower wick is >= body.
    bars.append(ResearchBar(start + timedelta(minutes=27), 100.0055, 100.0075, 100.004, 100.007, 100.0))
    bars.append(ResearchBar(start + timedelta(minutes=28), 100.007, 100.009, 100.007, 100.009, 100.0))
    return bars


def test_adapter_preserves_ohlc_and_does_not_import_volume_into_execution_bars():
    bars = _bars()
    execution = to_backtest_bars(bars, spread=0.0002)

    assert execution[-1].open == pytest.approx(bars[-1].open)
    assert execution[-1].high == pytest.approx(bars[-1].high)
    assert execution[-1].low == pytest.approx(bars[-1].low)
    assert execution[-1].close == pytest.approx(bars[-1].close)
    assert execution[-1].spread == pytest.approx(0.0002)


def test_breakout_retest_runs_through_real_backtest_engine():
    result = run_breakout_retest_backtest(
        _bars(),
        BreakoutRetestBacktestConfig(
            pip_size=0.0001,
            volume=0.03,
            point_value=1.0,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.direction is Direction.BUY
    assert trade.tag == "breakout_retest"
    assert trade.entry == pytest.approx(100.007)
    assert trade.exit == pytest.approx(100.009)
    assert trade.exit_reason in {"TP1", "TP2", "TP3", "EOD", "TP", "SL"}
    assert result.stats.trades == 1


def test_breakout_retest_boundary_allows_warmup_but_blocks_pre_boundary_signal():
    bars = _bars()
    config = BreakoutRetestBacktestConfig(pip_size=0.0001, point_value=1.0)

    warmup_orders = build_breakout_retest_orders(bars, config, min_signal_index=27)
    blocked_orders = build_breakout_retest_orders(bars, config, min_signal_index=28)

    assert len(warmup_orders) == 1
    assert warmup_orders[0].signal_time == bars[27].timestamp
    assert blocked_orders == ()


def test_backtest_requires_explicit_point_value():
    config = BreakoutRetestBacktestConfig(pip_size=0.0001)
    with pytest.raises(ValueError, match="point_value must be explicitly provided"):
        config.validate()


def test_backtest_rejects_invalid_economics():
    invalid_configs = (
        BreakoutRetestBacktestConfig(pip_size=0.0, point_value=1.0),
        BreakoutRetestBacktestConfig(pip_size=0.0001, volume=0.0, point_value=1.0),
        BreakoutRetestBacktestConfig(pip_size=0.0001, spread=-0.1, point_value=1.0),
        BreakoutRetestBacktestConfig(pip_size=0.0001, slippage=-0.1, point_value=1.0),
        BreakoutRetestBacktestConfig(pip_size=0.0001, point_value=0.0),
        BreakoutRetestBacktestConfig(pip_size=0.0001, commission_per_volume=-0.1, point_value=1.0),
    )
    for config in invalid_configs:
        with pytest.raises(ValueError):
            config.validate()


def test_backtest_timeframe_is_explicitly_carried_into_orders():
    config = BreakoutRetestBacktestConfig(
        pip_size=0.0001,
        point_value=1.0,
        timeframe=Timeframe.H1,
    )
    orders = build_breakout_retest_orders(_bars(), config)
    assert orders
    assert orders[0].selected_frame is Timeframe.H1


def test_negative_spread_is_rejected():
    with pytest.raises(ValueError):
        to_backtest_bars(_bars(), spread=-0.1)
