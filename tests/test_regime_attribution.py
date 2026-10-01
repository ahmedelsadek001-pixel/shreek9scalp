from core.backtest_engine import BacktestTrade
from core.enums import Direction
from research.regime import Regime
from research.regime_attribution import attribute_by_regime


def trade(pnl):
    return BacktestTrade(None, None, None, Direction.BUY, 100.0, 101.0, 1.0, pnl, 0.0, pnl, "TP")


def test_regime_attribution():
    rows = attribute_by_regime([trade(2.0), trade(-1.0), trade(3.0)], [Regime.TREND, Regime.RANGE, Regime.TREND])
    assert [row.regime for row in rows] == ["RANGE", "TREND"]
    assert rows[1].trades == 2
    assert rows[1].net_pnl == 5.0
    assert rows[1].expectancy == 2.5


def test_length_mismatch_fails_closed():
    try:
        attribute_by_regime([trade(1.0)], [Regime.TREND, Regime.RANGE])
    except ValueError as exc:
        assert "equal length" in str(exc)
    else:
        raise AssertionError("expected ValueError")
