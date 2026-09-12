"""Research-only edge matrix combining setup attribution and market regime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.backtest_engine import BacktestTrade
from research.regime import Regime


@dataclass(frozen=True)
class EdgeCell:
    setup: str
    regime: str
    trades: int
    wins: int
    losses: int
    net_pnl: float
    expectancy: float
    win_rate: float

    @property
    def viable(self) -> bool:
        return self.trades > 0 and self.expectancy > 0


def build_edge_matrix(
    trades: Iterable[BacktestTrade],
    regimes: Iterable[Regime | str],
    *,
    min_trades: int = 1,
) -> tuple[EdgeCell, ...]:
    """Aggregate recorded outcomes by setup tag and aligned regime labels."""
    if min_trades < 1:
        raise ValueError("min_trades must be at least 1")
    trade_list = list(trades)
    regime_list = list(regimes)
    if len(trade_list) != len(regime_list):
        raise ValueError("trades and regimes must have equal length")

    groups: dict[tuple[str, str], list[BacktestTrade]] = {}
    for trade, regime in zip(trade_list, regime_list):
        setup = trade.tag or "UNTAGGED"
        regime_name = regime.value if isinstance(regime, Regime) else str(regime).strip() or Regime.UNKNOWN.value
        groups.setdefault((setup, regime_name), []).append(trade)

    rows: list[EdgeCell] = []
    for (setup, regime_name), group in groups.items():
        if len(group) < min_trades:
            continue
        wins = sum(t.net_pnl > 0 for t in group)
        losses = sum(t.net_pnl < 0 for t in group)
        net = sum(t.net_pnl for t in group)
        rows.append(
            EdgeCell(setup, regime_name, len(group), wins, losses, net, net / len(group), wins / len(group) * 100)
        )
    return tuple(sorted(rows, key=lambda row: (row.setup, row.regime)))
