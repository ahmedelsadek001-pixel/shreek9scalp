"""Research-only risk-adjusted candidate ranking for SHREEK V5.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from research.edge_matrix import EdgeCell


@dataclass(frozen=True)
class SelectionScore:
    setup: str
    regime: str
    score: float
    confidence: str


def rank_edge_cells(cells: Iterable[EdgeCell], *, min_trades: int = 30) -> tuple[SelectionScore, ...]:
    """Rank sufficiently sampled cells using EV, win rate and sample depth.

    This is a research ranking, not an execution decision. Confidence labels
    are descriptive and never authorize a trade.
    """
    if min_trades < 1:
        raise ValueError("min_trades must be positive")
    rows: list[SelectionScore] = []
    for cell in cells:
        if cell.trades < min_trades:
            continue
        values = (cell.expectancy, cell.win_rate, float(cell.trades))
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("edge cell metrics must be finite")
        score = cell.expectancy * (cell.win_rate / 100.0) * min(2.0, cell.trades / min_trades)
        confidence = "HIGH" if cell.trades >= min_trades * 3 and cell.expectancy > 0 else "MEDIUM" if cell.expectancy > 0 else "LOW"
        rows.append(SelectionScore(cell.setup, cell.regime, score, confidence))
    return tuple(sorted(rows, key=lambda row: (-row.score, row.setup, row.regime)))
