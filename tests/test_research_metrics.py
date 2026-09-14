from datetime import datetime, timedelta

import pytest

from core.backtest_engine import (
    BacktestBar,
    BacktestOrder,
    BacktestResult,
    BacktestStats,
    BacktestTrade,
    CostModel,
    run_backtest,
)
from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.execution_levels import build_execution_levels
from core.models import TradeSignal
from core.research_metrics import calculate_research_metrics


def _levels():
    signal = TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.OB_ENTRY,
        frame=Timeframe.M5,
        direction=Direction.BUY,
        entry_price=100.0,
        sl_price=99.0,
    )
    return build_execution_levels(signal, min_rr=2.0)


def _bars():
    start = datetime(2026, 1, 1)
    rows = (
        (100, 100, 100, 100),
        (100, 102.1, 100, 102),
        (102, 102, 102, 102),
        (102, 102, 100, 100),
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 103.1, 100, 103),
    )
    return [BacktestBar(start + timedelta(minutes=i), *row) for i, row in enumerate(rows)]


def test_metrics_are_derived_from_realized_trade_pnl():
    series = _bars()
    result = run_backtest(
        series,
        [
            BacktestOrder(series[0].timestamp, Direction.BUY, _levels()),
            BacktestOrder(series[4].timestamp, Direction.BUY, _levels()),
        ],
        costs=CostModel(),
    )
    metrics = calculate_research_metrics(result)
    assert metrics.trades == 2
    assert metrics.wins == 2
    assert metrics.losses == 0
    assert metrics.win_rate_pct == 100.0
    assert metrics.expectancy == pytest.approx(metrics.net_pnl / 2)
    assert metrics.max_drawdown == 0.0
    assert metrics.profit_factor == float("inf")
    assert metrics.payoff_ratio == float("inf")


def test_metrics_preserve_cost_aware_net_pnl():
    series = _bars()
    result = run_backtest(
        series,
        [BacktestOrder(series[0].timestamp, Direction.BUY, _levels())],
        costs=CostModel(commission_per_volume=0.5),
    )
    metrics = calculate_research_metrics(result)
    assert metrics.net_pnl == pytest.approx(result.stats.net_pnl)
    assert metrics.expectancy == pytest.approx(result.stats.net_pnl)


def test_average_win_and_loss_are_arithmetic_means():
    start = datetime(2026, 1, 1)
    trades = (
        BacktestTrade(start, start, start, Direction.BUY, 100, 101, 1, 1, 0, 1, "TP"),
        BacktestTrade(start, start, start, Direction.BUY, 100, 104, 1, 4, 0, 4, "TP"),
        BacktestTrade(start, start, start, Direction.BUY, 100, 99, 1, -1, 0, -1, "SL"),
        BacktestTrade(start, start, start, Direction.BUY, 100, 98, 1, -2, 0, -2, "SL"),
    )
    result = BacktestResult(
        trades,
        (10000.0, 10001.0, 10005.0, 10004.0, 10002.0),
        BacktestStats(10000.0, 10002.0, 2.0, 0.02, 4, 2, 2, 50.0, 1.6666666667, 0.5, 3.0, 0.03, 1.0),
    )
    metrics = calculate_research_metrics(result)
    assert metrics.average_win == pytest.approx(2.5)
    assert metrics.average_loss == pytest.approx(1.5)
    assert metrics.payoff_ratio == pytest.approx(2.5 / 1.5)


def test_invalid_result_type_fails_closed():
    with pytest.raises(ValueError, match="BacktestResult"):
        calculate_research_metrics(object())
