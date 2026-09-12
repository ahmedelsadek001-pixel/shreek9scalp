from research.edge_matrix import EdgeCell
from research.selection_score import rank_edge_cells


def cell(setup, regime, trades, expectancy, win_rate):
    return EdgeCell(setup, regime, trades, 0, 0, expectancy * trades, expectancy, win_rate, trades)


def test_rank_edge_cells_prefers_positive_deeper_samples():
    rows = rank_edge_cells([
        cell("FVG", "TREND", 90, 1.0, 60.0),
        cell("OB", "RANGE", 30, 2.0, 70.0),
    ])
    assert rows[0].setup == "FVG"
    assert rows[0].confidence == "HIGH"


def test_sparse_cells_are_excluded():
    assert rank_edge_cells([cell("FVG", "TREND", 10, 4.0, 90.0)]) == ()
