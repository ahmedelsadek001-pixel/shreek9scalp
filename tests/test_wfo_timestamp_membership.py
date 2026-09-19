from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.backtest_wfo import run_backtest_wfo


START = datetime(2026, 1, 1)


def _result(signal_minute=5, entry_minute=5, exit_minute=6):
    trade = BacktestTrade(
        START + timedelta(minutes=signal_minute),
        START + timedelta(minutes=entry_minute),
        START + timedelta(minutes=exit_minute),
        Direction.BUY, 100.0, 101.0, 1.0, 1.0, 0.0, 1.0, "TP3",
    )
    stats = BacktestStats(
        10000.0, 10001.0, 1.0, 0.01, 1, 1, 0, 100.0,
        float("inf"), 1.0, 0.0, 0.0, 0.0,
    )
    return BacktestResult((trade,), (10000.0, 10001.0), stats)


@pytest.mark.parametrize(
    ("signal", "entry", "exit"),
    [(5.5, 5.5, 6), (5, 5.5, 6), (5, 5, 5.5)],
)
def test_wfo_rejects_trade_timestamps_not_present_in_oos_bars(signal, entry, exit):
    data = [SimpleNamespace(timestamp=START + timedelta(minutes=i)) for i in range(9)]

    def evaluator(rows, params):
        return _result(signal, entry, exit)

    with pytest.raises(ValueError, match="must match observed OOS bars"):
        run_backtest_wfo(
            data, ({"x": 1},), evaluator,
            train_size=4, test_size=2, purge_size=1, step=2,
        )


def test_wfo_accepts_trade_timestamps_present_in_oos_bars():
    data = [SimpleNamespace(timestamp=START + timedelta(minutes=i)) for i in range(9)]

    def evaluator(rows, params):
        return _result(5, 5, 6)

    result = run_backtest_wfo(
        data, ({"x": 1},), evaluator,
        train_size=4, test_size=2, purge_size=1, step=2,
    )
    assert result.oos_results[0].trades[0].exit_time == START + timedelta(minutes=6)
