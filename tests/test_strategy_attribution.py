from core.backtest_engine import BacktestTrade
from core.enums import Direction
from research.strategy_attribution import attribute_by_tag


def trade(tag, pnl):
    return BacktestTrade(None, None, None, Direction.BUY, 100.0, 101.0, 1.0, pnl, 0.0, pnl, "TP", tag)


def test_attribution_groups_and_sorts_tags():
    rows = attribute_by_tag([trade("FVG", 2.0), trade("OB", -1.0), trade("FVG", 4.0)])
    assert [row.tag for row in rows] == ["FVG", "OB"]
    assert rows[0].trades == 2
    assert rows[0].net_pnl == 6.0
    assert rows[0].win_rate == 100.0
    assert rows[1].losses == 1


def test_untagged_trades_are_explicit():
    rows = attribute_by_tag([trade("", 1.0)])
    assert rows[0].tag == "UNTAGGED"
