from datetime import datetime, time, timedelta
import pytest
from core.backtest_engine import BacktestBar, BacktestOrder, CostModel, IntrabarPolicy, run_backtest
from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.execution_levels import build_execution_levels
from core.models import TradeSignal
from core.position_lifecycle import LifecyclePolicy
from core.trading_window import SessionWindow, TradingWindowPolicy


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
    series = bars([(100, 105, 95, 100, 0), (101, 101, 100, 100, 0), (102, 103, 101, 102, 0)])
    result = run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.BUY, levels())])
    assert result.trades[0].entry_time == series[1].timestamp
    assert result.trades[0].entry == 101.0


def test_ambiguous_bar_resolves_stop_first_by_default():
    series = bars([(100, 100, 100, 100, 0), (100, 100, 100, 100, 0), (100, 103, 97, 100, 0)])
    result = run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.BUY, levels())])
    assert result.trades[0].exit_reason == "SL"
    assert result.trades[0].net_pnl < 0


def test_ambiguous_bar_can_resolve_target_first():
    series = bars([(100, 100, 100, 100, 0), (100, 100, 100, 100, 0), (100, 103, 97, 100, 0)])
    result = run_backtest(
        series,
        [BacktestOrder(series[0].timestamp, Direction.BUY, levels())],
        intrabar_policy=IntrabarPolicy.TARGET_FIRST,
    )
    assert result.trades[0].exit_reason == "TP"
    assert result.trades[0].net_pnl > 0


def test_ambiguous_bar_can_be_skipped():
    series = bars([(100, 100, 100, 100, 0), (100, 100, 100, 100, 0), (100, 103, 97, 100, 0), (100, 100, 100, 100, 0)])
    result = run_backtest(
        series,
        [BacktestOrder(series[0].timestamp, Direction.BUY, levels())],
        intrabar_policy=IntrabarPolicy.SKIP_AMBIGUOUS,
    )
    assert result.trades[0].exit_reason == "EOD"


def test_invalid_intrabar_policy_fails_closed():
    series = bars([(100, 100, 100, 100, 0), (100, 101, 99, 100, 0)])
    with pytest.raises(ValueError, match="invalid intrabar policy"):
        run_backtest(series, [], intrabar_policy="UNKNOWN")


def test_spread_slippage_and_commission_reduce_pnl():
    series = bars([(100, 100, 100, 100, 0), (100, 103, 100, 102, 0.2), (102, 103, 102, 103, 0.2)])
    result = run_backtest(
        series,
        [BacktestOrder(series[0].timestamp, Direction.BUY, levels())],
        costs=CostModel(slippage=0.1, point_value=1, commission_per_volume=0.5),
    )
    assert result.trades[0].costs > 0
    assert result.stats.net_pnl < 3.0


def test_invalid_ohlc_fails_closed():
    series = bars([(100, 99, 98, 99, 0), (99, 100, 98, 99, 0)])
    with pytest.raises(ValueError, match="invalid or empty"):
        run_backtest(series, [])


def test_invalid_chronology_fails_closed():
    series = bars([(100, 101, 99, 100, 0), (100, 101, 99, 100, 0)])
    series.reverse()
    with pytest.raises(ValueError, match="chronological"):
        run_backtest(series, [])


def test_unknown_order_direction_rejected():
    series = bars([(100, 101, 99, 100, 0), (100, 101, 99, 100, 0)])
    with pytest.raises(ValueError, match="BUY or SELL"):
        run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.RANGE, levels())])


def test_direction_mismatch_in_levels_fails_closed():
    series = bars([(100, 100, 100, 100, 0), (100, 101, 99, 100, 0)])
    with pytest.raises(ValueError, match="inconsistent"):
        run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.SELL, levels(Direction.BUY))])


def test_lifecycle_realizes_tp1_tp2_tp3_and_records_events():
    series = bars([
        (100, 100, 100, 100, 0),
        (100, 101.1, 100, 101, 0),
        (101, 102.1, 100.9, 102, 0),
        (102, 103.1, 101.9, 103, 0),
    ])
    policy = LifecyclePolicy(tp1_fraction=0.5, tp2_fraction=0.25, tp3_fraction=0.25)
    result = run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.BUY, levels())], lifecycle_policy=policy)
    trade = result.trades[0]
    assert trade.exit_reason == "TP3"
    assert trade.volume == 1.0
    assert trade.lifecycle_events == ("TP1", "TP2", "TP3")
    assert trade.net_pnl > 0


def test_lifecycle_commission_is_charged_once_per_execution_leg():
    series = bars([
        (100, 100, 100, 100, 0),
        (100, 101.1, 100, 101, 0),
        (101, 102.1, 100.9, 102, 0),
        (102, 103.1, 101.9, 103, 0),
    ])
    policy = LifecyclePolicy(tp1_fraction=0.5, tp2_fraction=0.25, tp3_fraction=0.25)
    result = run_backtest(
        series,
        [BacktestOrder(series[0].timestamp, Direction.BUY, levels())],
        lifecycle_policy=policy,
        costs=CostModel(commission_per_volume=2.0),
    )
    trade = result.trades[0]
    assert trade.costs == pytest.approx(4.0)


def test_lifecycle_stop_after_tp1_uses_breakeven_on_following_bar():
    series = bars([(100, 100, 100, 100, 0), (100, 101.1, 100, 101, 0), (101, 101.0, 99.9, 100, 0)])
    result = run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.BUY, levels())], lifecycle_policy=LifecyclePolicy())
    trade = result.trades[0]
    assert trade.exit_reason == "SL"
    assert trade.lifecycle_events == ("TP1",)
    assert trade.net_pnl > -0.1


def test_lifecycle_trailing_activates_after_tp2_and_exits_on_next_bar():
    series = bars([
        (100, 100, 100, 100, 0),
        (100, 101.1, 100, 101, 0),
        (101, 102.1, 100.9, 102, 0),
        (102, 102.5, 100.9, 101.5, 0),
    ])
    policy = LifecyclePolicy(trailing_after_tp2=True, trailing_distance_r=1.0)
    result = run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.BUY, levels())], lifecycle_policy=policy)
    trade = result.trades[0]
    assert trade.exit_reason == "SL"
    assert trade.lifecycle_events == ("TP1", "TP2")
    assert trade.net_pnl > 0


def test_session_window_blocks_entry_outside_allowed_period():
    series = bars([(100, 100, 100, 100, 0), (100, 101, 99, 100, 0), (100, 101, 99, 100, 0)])
    policy = TradingWindowPolicy((SessionWindow("NY", time(13), time(14)),))
    result = run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.BUY, levels())], trading_window=policy)
    assert result.trades == ()


def test_max_holding_exits_at_bar_open_without_lookahead():
    series = bars([
        (100, 100, 100, 100, 0),
        (100, 100, 100, 100, 0),
        (105, 110, 104, 109, 0),
    ])
    policy = TradingWindowPolicy(max_holding_minutes=1)
    result = run_backtest(series, [BacktestOrder(series[0].timestamp, Direction.BUY, levels())], trading_window=policy)
    trade = result.trades[0]
    assert trade.exit_reason == "TIME"
    assert trade.exit_time == series[2].timestamp
    assert trade.exit == 105.0


def test_backtest_rejects_non_datetime_bar_timestamp():
    series = [
        BacktestBar("2026-01-01", 100, 101, 99, 100, 0),
        BacktestBar(datetime(2026, 1, 1, 0, 1), 100, 101, 99, 100, 0),
    ]
    with pytest.raises(ValueError, match="bar timestamp"):
        run_backtest(series, [])


def test_backtest_rejects_mixed_bar_timestamp_timezone_awareness():
    series = [
        BacktestBar(datetime(2026, 1, 1), 100, 101, 99, 100, 0),
        BacktestBar(datetime(2026, 1, 1, 0, 1, tzinfo=__import__("datetime").timezone.utc), 100, 101, 99, 100, 0),
    ]
    with pytest.raises(ValueError, match="timezone awareness"):
        run_backtest(series, [])


def test_backtest_rejects_order_timestamp_timezone_mismatch():
    series = bars([(100, 101, 99, 100, 0), (100, 101, 99, 100, 0)])
    aware_signal = datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc)
    with pytest.raises(ValueError, match="timezone awareness"):
        run_backtest(series, [BacktestOrder(aware_signal, Direction.BUY, levels())])
