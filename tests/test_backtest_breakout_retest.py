from datetime import datetime, timedelta, timezone

import pytest

from core.enums import Direction
from research.backtest_breakout_retest import (
    BreakoutRetestBacktestConfig,
    run_breakout_retest_backtest,
    to_backtest_bars,
)
from research.breakout_retest import ResearchBar


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
    # Bullish pin-bar style retest: it touches the breakout level and closes strongly.
    bars.append(ResearchBar(start + timedelta(minutes=27), 100.005, 100.007, 100.0045, 100.0065, 100.0))
    bars.append(ResearchBar(start + timedelta(minutes=28), 100.007, 100.010, 100.006, 100.009, 100.0))
    return bars


def test_research_bars_convert_without_volume_leakage():
    bars = to_backtest_bars(_bars(), spread=0.0002)
    assert len(bars) == len(_bars())
    assert bars[-1].spread == pytest.approx(0.0002)
    assert not hasattr(bars[-1], "volume")


def test_breakout_retest_runs_through_real_backtest_engine():
    result = run_breakout_retest_backtest(
        _bars(),
        BreakoutRetestBacktestConfig(pip_size=0.0001, volume=0.03),
    )

    assert result.stats.trades == 1
    assert result.trades[0].direction is Direction.BUY
    assert result.trades[0].tag == "breakout_retest"
    assert result.trades[0].exit_reason in {"TP", "SL", "EOD"}
    assert result.stats.ending_equity == pytest.approx(10000.0 + result.trades[0].net_pnl)


def test_negative_spread_is_rejected():
    with pytest.raises(ValueError):
        to_backtest_bars(_bars(), spread=-0.0001)
