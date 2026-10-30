from research.edge_matrix import EdgeCell
from research.edge_selection import EdgeSelectionPolicy, select_candidates


def cell(setup, regime, trades, expectancy, win_rate):
    return EdgeCell(setup, regime, trades, 0, 0, expectancy * trades, expectancy, win_rate, 1)


def test_select_candidates_filters_weak_cells():
    rows = select_candidates([
        cell("FVG", "TREND", 40, 1.0, 50.0),
        cell("OB", "RANGE", 20, 2.0, 80.0),
        cell("SWEEP", "TREND", 50, -0.5, 60.0),
    ])
    assert [(row.setup, row.regime) for row in rows] == [("FVG", "TREND")]


def test_policy_validation():
    try:
        select_candidates([], EdgeSelectionPolicy(min_win_rate=101.0))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
