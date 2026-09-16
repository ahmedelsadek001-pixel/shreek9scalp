from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.backtest_wfo import run_backtest_wfo


class _TimedValue(int):
    def __new__(cls, value, timestamp):
        obj = int.__new__(cls, value)
        obj.timestamp = timestamp
        return obj


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


def _timed_result(signal_minute: int, entry_minute: int, exit_minute: int) -> BacktestResult:
    start = datetime(2026, 1, 1)
    signal_time = start + timedelta(minutes=signal_minute)
    entry_time = start + timedelta(minutes=entry_minute)
    exit_time = start + timedelta(minutes=exit_minute)
    trade = BacktestTrade(
        signal_time,
        entry_time,
        exit_time,
        Direction.BUY,
        100.0,
        101.0,
        1.0,
        1.0,
        0.0,
        1.0,
        "TP3",
    )
    stats = BacktestStats(
        10000.0,
        10001.0,
        1.0,
        0.01,
        1,
        1,
        0,
        100.0,
        float("inf"),
        1.0,
        0.0,
        0.0,
        0.0,
    )
    return BacktestResult((trade,), (10000.0, 10001.0), stats)


def test_wfo_selects_from_train_metrics_and_returns_real_oos_results():
    data = list(range(9))
    params = ({"mult": 1.0}, {"mult": 2.0})

    def evaluator(rows, selected):
        return _result(sum(rows) * selected["mult"])

    result = run_backtest_wfo(
        data, params, evaluator, train_size=4, test_size=2, purge_size=1, step=2
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
        data, params, evaluator, train_size=4, test_size=2, purge_size=1, step=2
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
        data, params, evaluator, train_size=4, test_size=2, purge_size=1, step=2
    )

    assert len(result.oos_results) == 2
    assert calls.count((5, 6)) == 1
    assert calls.count((7, 8)) == 1


def test_wfo_warmup_passes_timestamped_context_and_defines_oos_boundary():
    start = datetime(2026, 1, 1)
    data = [_TimedValue(i, start + timedelta(minutes=i)) for i in range(9)]
    params = ({"mult": 1.0},)
    oos_calls = []

    def evaluator(rows, selected):
        return _result(sum(rows) * selected["mult"])

    def context_evaluator(rows, selected, oos_start_index):
        rows = tuple(rows)
        oos_values = tuple(int(row) for row in rows[oos_start_index:])
        oos_calls.append((tuple(int(row) for row in rows), oos_start_index))
        assert oos_values in (tuple(range(5, 7)), tuple(range(7, 9)))
        signal_minute = oos_values[0]
        exit_minute = oos_values[-1]
        return _timed_result(signal_minute, signal_minute, exit_minute)

    result = run_backtest_wfo(
        data,
        params,
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        step=2,
        context_size=2,
        context_evaluator=context_evaluator,
    )

    assert len(result.oos_results) == 2
    assert oos_calls == [((3, 4, 5, 6), 2), ((5, 6, 7, 8), 2)]


def test_wfo_context_rejects_trade_signal_before_oos_boundary():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]

    def evaluator(rows, selected):
        return _result(1.0)

    def leaking_context_evaluator(rows, selected, oos_start_index):
        return _result(1.0)

    with pytest.raises(ValueError, match="outside the OOS boundary"):
        run_backtest_wfo(
            data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1,
            step=2, context_size=2, context_evaluator=leaking_context_evaluator,
        )


def test_wfo_context_rejects_trade_entry_before_oos_boundary():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]

    def evaluator(rows, selected):
        return _result(1.0)

    def leaking_context_evaluator(rows, selected, oos_start_index):
        return _timed_result(5, 4, 5)

    with pytest.raises(ValueError, match="outside the OOS boundary"):
        run_backtest_wfo(
            data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1,
            step=2, context_size=2, context_evaluator=leaking_context_evaluator,
        )


def test_wfo_context_rejects_trade_exit_after_oos_boundary():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]

    def evaluator(rows, selected):
        return _result(1.0)

    def leaking_context_evaluator(rows, selected, oos_start_index):
        return _timed_result(5, 6, 7)

    with pytest.raises(ValueError, match="outside the OOS boundary"):
        run_backtest_wfo(
            data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1,
            step=2, context_size=2, context_evaluator=leaking_context_evaluator,
        )


def test_wfo_context_rejects_non_chronological_trade_timestamps():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]

    def evaluator(rows, selected):
        return _result(1.0)

    def invalid_context_evaluator(rows, selected, oos_start_index):
        return _timed_result(5, 7, 6)

    with pytest.raises(ValueError, match="non-chronological"):
        run_backtest_wfo(
            data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1,
            step=2, context_size=2, context_evaluator=invalid_context_evaluator,
        )


def test_wfo_context_rejects_missing_timestamps_fail_closed():
    def evaluator(rows, selected):
        return _result(1.0)

    def context_evaluator(rows, selected, oos_start_index):
        return _result(1.0)

    with pytest.raises(ValueError, match="must expose timestamp"):
        run_backtest_wfo(
            list(range(8)), ({"x": 1},), evaluator, train_size=3, test_size=2,
            purge_size=1, context_size=1, context_evaluator=context_evaluator,
        )


def test_wfo_context_requires_timestamps_even_when_no_oos_trades():
    data = list(range(8))

    def evaluator(rows, selected):
        return _result(1.0)

    def empty_context_evaluator(rows, selected, oos_start_index):
        stats = BacktestStats(10000.0, 10000.0, 0.0, 0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return BacktestResult((), (10000.0,), stats)

    with pytest.raises(ValueError, match="must expose timestamp"):
        run_backtest_wfo(
            data, ({"x": 1},), evaluator, train_size=3, test_size=2,
            purge_size=1, context_size=1, context_evaluator=empty_context_evaluator,
        )


def test_wfo_context_rejects_incomparable_timestamps_fail_closed():
    data = [SimpleNamespace(timestamp=datetime(2026, 1, 1) + timedelta(minutes=i)) for i in range(8)]

    def evaluator(rows, selected):
        return _result(1.0)

    def context_evaluator(rows, selected, oos_start_index):
        return _timed_result(3, 4, 5)

    data[4].timestamp = "not-a-timestamp"
    with pytest.raises(ValueError, match="mutually comparable"):
        run_backtest_wfo(
            data, ({"x": 1},), evaluator, train_size=3, test_size=2,
            purge_size=1, context_size=1, context_evaluator=context_evaluator,
        )


def test_wfo_requires_context_evaluator_when_warmup_is_requested():
    with pytest.raises(ValueError, match="context_evaluator is required"):
        run_backtest_wfo(
            list(range(8)), ({"x": 1},), lambda rows, selected: _result(1.0),
            train_size=3, test_size=2, purge_size=1, context_size=1,
        )
