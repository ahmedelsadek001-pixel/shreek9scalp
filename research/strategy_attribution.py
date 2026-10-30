"""Deterministic strategy-attribution analytics for SHREEK V5.2 research.

Research-only: summarizes already-recorded trades and never routes orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from core.backtest_engine import BacktestTrade


@dataclass(frozen=True)
class AttributionRow:
    tag: str
    trades: int
    wins: int
    losses: int
    net_pnl: float
    expectancy: float
    win_rate: float


def attribute_by_tag(trades: Iterable[BacktestTrade]) -> tuple[AttributionRow, ...]:
    """Aggregate backtest performance by strategy/setup tag."""
    groups: dict[str, list[BacktestTrade]] = {}
    for trade in trades:
        if not isfinite(float(trade.net_pnl)):
            raise ValueError("trade net_pnl must be finite")
        groups.setdefault(trade.tag or "UNTAGGED", []).append(trade)

    rows = []
    for tag, group in groups.items():
        wins = sum(t.net_pnl > 0 for t in group)
        losses = sum(t.net_pnl < 0 for t in group)
        net = sum(t.net_pnl for t in group)
        rows.append(
            AttributionRow(
                tag=tag,
                trades=len(group),
                wins=wins,
                losses=losses,
                net_pnl=net,
                expectancy=net / len(group),
                win_rate=wins / len(group) * 100,
            )
        )
    return tuple(sorted(rows, key=lambda row: row.tag))
