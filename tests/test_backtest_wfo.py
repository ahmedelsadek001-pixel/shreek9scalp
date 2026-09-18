from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.backtest_wfo import run_backtest_wfo


def _result(pnl: float) -> BacktestResult:
    now = datetime(2026, 1, 1)
    trade = BacktestTrade(now, now + timedelta(minutes=1), now + timedelta(minutes=2), Direction.BUY, 100.0, 100.0 + pnl, 1.0, pnl, 0.0, pnl, "TP3" if pnl > 0 else "SL")
    stats = BacktestStats(10000.0, 10000.0 + pnl, pnl, pnl / 10000.0 * 100.0, 1, int(pnl > 0), int(pnl < 0), 100.0 if pnl > 0 else 0.0, float("inf") if pnl > 0 else 0.0, pnl, max(-pnl, 0.0), max(-pnl, 0.0) / 10000.0 * 100.0, 0.0)
    return BacktestResult((trade,), (10000.0, 10000.0 + pnl), stats)


def test_wfo_selects_from_train_metrics_and_returns_real_oos_results():
    data = list(range(9))
    params = ({"mult": 1.0}, {"mult": 2.0})
    def evaluator(rows, selected): return _result(sum(rows) * selected["mult"])
    result = run_backtest_wfo(data, params, evaluator, train_size=4, test_size=2, purge_size=1, step=2)
    assert len(result.oos_results) == 2
    assert result.validation.windows[0].test_start == 5
    assert result.validation.windows[0].test_end == 7
    assert result.validation.selected_parameters[0] == {"mult": 2.0}


def test_wfo_objective_is_based_only_on_train_metrics():
    data = [10, 10, 1, 1, -100, -100, 1, 1, 1]
    params = ({"mult": 1.0}, {"mult": -1.0})
    calls = []
    def evaluator(rows, selected): calls.append(tuple(rows)); return _result(sum(rows) * selected["mult"])
    result = run_backtest_wfo(data, params, evaluator, train_size=4, test_size=2, purge_size=1, step=2)
    assert result.validation.selected_parameters[0] == {"mult": 1.0}
    assert tuple(data[4:5]) not in calls
    assert result.oos_results[0].trades[0].net_pnl == -99.0


def test_wfo_evaluates_each_selected_oos_slice_once():
    data = list(range(9)); calls = []
    def evaluator(rows, selected): calls.append(tuple(rows)); return _result(sum(rows) * selected["mult"])
    result = run_backtest_wfo(data, ({"mult": 1.0},), evaluator, train_size=4, test_size=2, purge_size=1, step=2)
    assert len(result.oos_results) == 2
    assert calls.count((5, 6)) == 1
    assert calls.count((7, 8)) == 1


def _timed_result(signal_minute, entry_minute, exit_minute):
    start = datetime(2026, 1, 1)
    trade = BacktestTrade(start + timedelta(minutes=signal_minute), start + timedelta(minutes=entry_minute), start + timedelta(minutes=exit_minute), Direction.BUY, 100.0, 101.0, 1.0, 1.0, 0.0, 1.0, "TP3")
    stats = BacktestStats(10000.0, 10001.0, 1.0, 0.01, 1, 1, 0, 100.0, float("inf"), 1.0, 0.0, 0.0, 0.0)
    return BacktestResult((trade,), (10000.0, 10001.0), stats)


def test_wfo_warmup_passes_timestamped_context_and_defines_oos_boundary():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(value=i, timestamp=start + timedelta(minutes=i)) for i in range(9)]
    calls = []
    def evaluator(rows, selected): return _result(sum(row.value for row in rows) * selected["mult"])
    def context_evaluator(rows, selected, oos_start_index):
        calls.append((tuple(row.value for row in rows), oos_start_index))
        oos = rows[oos_start_index:]
        return _timed_result(oos[0].value, oos[0].value, oos[-1].value)
    result = run_backtest_wfo(data, ({"mult": 1.0},), evaluator, train_size=4, test_size=2, purge_size=1, step=2, context_size=2, context_evaluator=context_evaluator)
    assert len(result.oos_results) == 2
    assert calls == [((3, 4, 5, 6), 2), ((5, 6, 7, 8), 2)]


def test_wfo_context_rejects_future_exit():
    start = datetime(2026, 1, 1); data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]
    def evaluator(rows, selected): return _result(1.0)
    def leaking(rows, selected, index): return _timed_result(5, 5, 7)
    with pytest.raises(ValueError, match="outside the OOS interval"):
        run_backtest_wfo(data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1, step=2, context_size=2, context_evaluator=leaking)


def test_wfo_context_rejects_pre_oos_entry():
    start = datetime(2026, 1, 1); data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]
    def evaluator(rows, selected): return _result(1.0)
    def leaking(rows, selected, index): return _timed_result(5, 4, 5)
    with pytest.raises(ValueError, match="outside the OOS interval"):
        run_backtest_wfo(data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1, step=2, context_size=2, context_evaluator=leaking)


def test_wfo_timestamped_oos_rejects_future_exit_without_context():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]
    def evaluator(rows, selected):
        return _timed_result(5, 5, 7)
    with pytest.raises(ValueError, match="outside the OOS interval"):
        run_backtest_wfo(data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1, step=2)


def test_wfo_timestamped_oos_rejects_pre_oos_signal_without_context():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(9)]
    def evaluator(rows, selected):
        return _timed_result(4, 5, 5)
    with pytest.raises(ValueError, match="outside the OOS interval"):
        run_backtest_wfo(data, ({"x": 1},), evaluator, train_size=4, test_size=2, purge_size=1, step=2)


def test_wfo_context_rejects_missing_timestamps_fail_closed():
    def evaluator(rows, selected): return _result(1.0)
    def context(rows, selected, index): return _result(1.0)
    with pytest.raises(ValueError, match="must expose timestamp"):
        run_backtest_wfo(list(range(8)), ({"x": 1},), evaluator, train_size=3, test_size=2, purge_size=1, context_size=1, context_evaluator=context)


def test_wfo_requires_context_evaluator_when_warmup_is_requested():
    with pytest.raises(ValueError, match="context_evaluator is required"):
        run_backtest_wfo(list(range(8)), ({"x": 1},), lambda rows, selected: _result(1.0), train_size=3, test_size=2, purge_size=1, context_size=1)


def test_wfo_context_rejects_malformed_result_before_boundary_access():
    start = datetime(2026, 1, 1)
    data = [SimpleNamespace(timestamp=start + timedelta(minutes=i)) for i in range(8)]
    def evaluator(rows, selected): return _result(1.0)
    def malformed(rows, selected, index): return object()
    with pytest.raises(ValueError, match="OOS evaluator must return a BacktestResult"):
        run_backtest_wfo(data, ({"x": 1},), evaluator, train_size=3, test_size=2, purge_size=1, context_size=1, context_evaluator=malformed)


def test_wfo_oos_result_is_invariant_to_future_data_mutation():
    data = list(range(12))
    def evaluator(rows, selected): return _result(sum(rows) * selected["mult"])
    baseline = run_backtest_wfo(data, ({"mult": 1.0},), evaluator, train_size=4, test_size=2, purge_size=1, step=2)
    mutated = list(data)
    first_oos_end = baseline.validation.windows[0].test_end
    mutated[first_oos_end:] = [value + 1000000 for value in mutated[first_oos_end:]]
    replay = run_backtest_wfo(mutated, ({"mult": 1.0},), evaluator, train_size=4, test_size=2, purge_size=1, step=2)
    assert baseline.oos_results[0] == replay.oos_results[0]
    assert baseline.oos_metrics[0] == replay.oos_metrics[0]
