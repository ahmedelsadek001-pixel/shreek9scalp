from datetime import datetime, timedelta

import pytest

from core.backtest_engine import BacktestBar, BacktestOrder, CostModel, run_backtest
from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.execution_levels import build_execution_levels
from core.models import TradeSignal


def levels(direction=Direction.BUY):
    signal = TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.OB_ENTRY,
        frame=Timeframe.M5,
        direction=direction,
        entry_price=100.0,
        sl_price=99.0 if direction == Direction.BUY else 101.0,
    )
    return build_execution_levels(signal, min_rr=2.0)


def bars(rows):
    start = datetime(2026, 1, 1)
    return [BacktestBar(start + timedelta(minutes=i), *row) for i, row in enumerate(rows)]


def test_entry_is_next_bar_not_signal_bar():
    series = bars([
        (100, 105, 95, 100, 0),
        (101, 101, 100, 100, 0),
        (102, 103, 101, 102, 0),
    ])
    order = BacktestOrder(series[0].timestamp, Direction.BUY, levels())
    result = run_backtest(series, [order], force_close_at_end=True)
    assert result.trades[0].entry_time == series[1].timestamp
    assert result.trades[0].entry == 101.0


def test_ambiguous_bar_resolves_stop_first():
    series = bars([
        (100, 100, 100, 100, 0),
        (100, 100, 100, 100, 0),
        (100, 103, 97, 100, 0),
    ])
    order = BacktestOrder(series[0].timestamp, Direction.BUY, levels())
    result = run_backtest(series, [order])
    assert result.trades[0].exit_reason == "SL"
    assert result.trades[0].net_pnl < 0


def test_spread_slippage_and_commission_reduce_pnl():
    series = bars([
        (100, 100, 100, 100, 0),
        (100, 103, 100, 102, 0.2),
        (102, 103, 102, 103, 0.2),
    ])
    order = BacktestOrder(series[0].timestamp, Direction.BUY, levels())
    result = run_backtest(series, [order], costs=CostModel(slippage=0.1, point_value=1.0, commission_per_volume=0.5))
    assert result.trades[0].costs > 0
    assert result.stats.net_pnl < 3.0


def test_invalid_chronology_fails_closed():
    series = bars([(100, 101, 99, 100, 0), (100, 101, 99, 100, 0)])
    series.reverse()
    with pytest.raises(ValueError, match="chronological"):
        run_backtest(series, [])


def test_unknown_order_direction_rejected():
    series = bars([(100, 101, 99, 100, 0), (100, 101, 99, 100, 0)])
    order = BacktestOrder(series[0].timestamp, Direction.RANGE, levels())
    with pytest.raises(ValueError, match="BUY or SELL"):
        run_backtest(series, [order])
