from core.backtest_engine import BacktestTrade
from core.enums import Direction
from research.edge_matrix import build_edge_matrix
from research.regime import Regime


def trade(tag, pnl):
    return BacktestTrade(None, None, None, Direction.BUY, 100.0, 101.0, 1.0, pnl, 0.0, pnl, "TP", tag)


def test_matrix_combines_setup_and_regime():
    rows = build_edge_matrix(
        [trade("FVG", 2.0), trade("FVG", -1.0), trade("OB", 4.0)],
        [Regime.TREND, Regime.TREND, Regime.RANGE],
    )
    assert [(r.setup, r.regime) for r in rows] == [("FVG", "TREND"), ("OB", "RANGE")]
    assert rows[0].expectancy == 0.5
    assert rows[1].viable is True


def test_matrix_min_trades_filters_sparse_cells():
    rows = build_edge_matrix([trade("FVG", 2.0)], [Regime.TREND], min_trades=2)
    assert rows == ()
