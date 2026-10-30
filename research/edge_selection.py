"""Conservative research gate for selecting candidate setup/regime cells."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from research.edge_matrix import EdgeCell


@dataclass(frozen=True)
class EdgeSelectionPolicy:
    min_trades: int = 30
    min_win_rate: float = 45.0
    min_expectancy: float = 0.0

    def validate(self) -> None:
        if self.min_trades < 1:
            raise ValueError("min_trades must be positive")
        if not 0 <= self.min_win_rate <= 100:
            raise ValueError("min_win_rate must be between 0 and 100")


def select_candidates(
    cells: Iterable[EdgeCell],
    policy: EdgeSelectionPolicy = EdgeSelectionPolicy(),
) -> tuple[EdgeCell, ...]:
    """Return only sufficiently sampled cells with positive expected value."""
    policy.validate()
    selected = [
        cell for cell in cells
        if cell.trades >= policy.min_trades
        and cell.win_rate >= policy.min_win_rate
        and cell.expectancy > policy.min_expectancy
    ]
    return tuple(sorted(selected, key=lambda cell: (-cell.expectancy, -cell.trades, cell.setup, cell.regime)))
