from datetime import datetime, timedelta

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.backtest_wfo import run_backtest_wfo


def _result(pnl: float) -> BacktestResult:
    now = datetime(2026, 1, 1)
    trade = BacktestTrade(
        now,
        now + timedelta(minutes=1),
        now + timedelta(minutes=2),
        Direction.BUY,
        100.0,
        100.0 + pnl,
        1.0,
        pnl,
        0.0,
        pnl,
        "TP3" if pnl > 0 else "SL",
    )
    stats = BacktestStats(
        10000.0,
        10000.0 + pnl,
        pnl,
        pnl / 10000.0 * 100.0,
        1,
        int(pnl > 0),
        int(pnl < 0),
        100.0 if pnl > 0 else 0.0,
        float("inf") if pnl > 0 else 0.0,
        pnl,
        max(-pnl, 0.0),
        max(-pnl, 0.0) / 10000.0 * 100.0,
        0.0,
    )
    return BacktestResult((trade,), (10000.0, 10000.0 + pnl), stats)


def test_wfo_selects_from_train_metrics_and_returns_real_oos_results():
    data = list(range(9))
    params = ({"mult": 1.0}, {"mult": 2.0})

    def evaluator(rows, selected):
        return _result(sum(rows) * selected["mult"])

    result = run_backtest_wfo(
        data,
        params,
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        step=2,
    )

    assert len(result.oos_results) == 2
    assert all(isinstance(item, BacktestResult) for item in result.oos_results)
    assert result.validation.windows[0].test_start == 5
    assert result.validation.windows[0].test_end == 7
    assert result.validation.selected_parameters[0] == {"mult": 2.0}
    assert result.train_metrics[0].expectancy > 0
    assert result.oos_net_pnl > 0
    assert result.oos_expectancy > 0
    assert result.oos_stability_pct == 100.0


def test_wfo_objective_is_based_only_on_train_metrics():
    data = [10, 10, 1, 1, -100, -100, 1, 1, 1]
    params = ({"mult": 1.0}, {"mult": -1.0})
    calls = []

    def evaluator(rows, selected):
        calls.append(tuple(rows))
        return _result(sum(rows) * selected["mult"])

    result = run_backtest_wfo(
        data,
        params,
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        step=2,
    )

    assert result.validation.selected_parameters[0] == {"mult": 1.0}
    assert tuple(data[4:5]) not in calls
    assert result.oos_results[0].trades[0].net_pnl == -99.0


def test_wfo_evaluates_each_selected_oos_slice_once():
    data = list(range(9))
    params = ({"mult": 1.0},)
    calls = []

    def evaluator(rows, selected):
        rows = tuple(rows)
        calls.append(rows)
        return _result(sum(rows) * selected["mult"])

    result = run_backtest_wfo(
        data,
        params,
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        step=2,
    )

    assert len(result.oos_results) == 2
    assert calls.count((5, 6)) == 1
    assert calls.count((7, 8)) == 1


def test_wfo_rejects_non_backtest_evaluator_output():
    with pytest.raises(ValueError, match="BacktestResult"):
        run_backtest_wfo(
            list(range(8)),
            ({"x": 1},),
            lambda rows, params: 1.0,
            train_size=3,
            test_size=2,
            purge_size=1,
        )
