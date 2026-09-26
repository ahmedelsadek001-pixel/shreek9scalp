from datetime import datetime, timedelta

import pytest

from core.backtest_engine import BacktestBar, BacktestOrder, CostModel, run_backtest
from core.enums import Direction, SetupType, Timeframe
from core.models import ExecutionLevels


def _levels() -> ExecutionLevels:
    return ExecutionLevels(
        entry=100.0,
        sl=99.0,
        tp1=102.0,
        tp2=103.0,
        tp3=104.0,
        risk=1.0,
        rr1=2.0,
        setup_type=SetupType.OB_ENTRY,
        confidence=1.0,
        selected_frame=Timeframe.M5,
    )


def _bars(*rows):
    start = datetime(2026, 1, 1)
    return [BacktestBar(start + timedelta(minutes=i), *row) for i, row in enumerate(rows)]


def _order(bars, volume=1.0):
    return BacktestOrder(bars[0].timestamp, Direction.BUY, _levels(), volume=volume)


def test_point_value_scales_gross_and_net_pnl():
    series = _bars(
        (100, 100, 100, 100, 0),
        (100, 102, 100, 102, 0),
        (102, 102, 102, 102, 0),
    )
    order = _order(series, volume=2.0)

    base = run_backtest(series, [order], costs=CostModel(point_value=1.0))
    scaled = run_backtest(series, [order], costs=CostModel(point_value=3.0))

    assert base.trades[0].gross_pnl == pytest.approx(4.0)
    assert scaled.trades[0].gross_pnl == pytest.approx(12.0)
    assert scaled.trades[0].net_pnl == pytest.approx(12.0)


def test_spread_and_slippage_are_applied_at_entry_and_exit():
    series = _bars(
        (100, 100, 100, 100, 0),
        (100, 102.5, 100, 102, 0.2),
        (102, 102, 102, 102, 0.2),
    )
    result = run_backtest(
        series,
        [_order(series, volume=2.0)],
        costs=CostModel(slippage=0.1, point_value=1.0),
    )
    trade = result.trades[0]

    assert trade.entry == pytest.approx(100.2)
    assert trade.exit == pytest.approx(101.8)
    assert trade.gross_pnl == pytest.approx(4.0)
    assert trade.costs == pytest.approx(0.8)
    assert trade.net_pnl == pytest.approx(3.2)


def test_commission_is_charged_for_entry_and_exit_volume():
    series = _bars(
        (100, 100, 100, 100, 0),
        (100, 102.5, 100, 102, 0),
        (102, 102, 102, 102, 0),
    )
    result = run_backtest(
        series,
        [_order(series, volume=2.0)],
        costs=CostModel(point_value=1.0, commission_per_volume=0.5),
    )
    trade = result.trades[0]

    assert trade.gross_pnl == pytest.approx(4.0)
    assert trade.costs == pytest.approx(2.0)
    assert trade.net_pnl == pytest.approx(2.0)


def test_volume_scales_pnl_without_changing_execution_prices():
    series = _bars(
        (100, 100, 100, 100, 0),
        (100, 102.5, 100, 102, 0),
        (102, 102, 102, 102, 0),
    )
    one = run_backtest(series, [_order(series, volume=1.0)])
    three = run_backtest(series, [_order(series, volume=3.0)])

    assert one.trades[0].entry == pytest.approx(100.0)
    assert three.trades[0].entry == pytest.approx(100.0)
    assert three.trades[0].gross_pnl == pytest.approx(one.trades[0].gross_pnl * 3.0)


def test_cost_model_rejects_non_finite_or_negative_values():
    invalid = (
        CostModel(slippage=-0.1),
        CostModel(slippage=float("nan")),
        CostModel(point_value=0.0),
        CostModel(point_value=float("inf")),
        CostModel(commission_per_volume=-0.1),
        CostModel(commission_per_volume=float("nan")),
    )
    for costs in invalid:
        assert not costs.valid()


def test_backtest_rejects_invalid_cost_model():
    series = _bars(
        (100, 100, 100, 100, 0),
        (100, 102.5, 100, 102, 0),
    )
    with pytest.raises(ValueError, match="invalid backtest configuration"):
        run_backtest(series, [_order(series)], costs=CostModel(point_value=0.0))
