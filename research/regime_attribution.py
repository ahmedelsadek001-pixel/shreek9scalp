"""Research-only aggregation of backtest outcomes by market regime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.backtest_engine import BacktestTrade
from research.regime import Regime


@dataclass(frozen=True)
class RegimeAttribution:
    regime: str
    trades: int
    wins: int
    losses: int
    net_pnl: float
    expectancy: float
    win_rate: float


def attribute_by_regime(
    trades: Iterable[BacktestTrade], regimes: Iterable[Regime | str]
) -> tuple[RegimeAttribution, ...]:
    """Aggregate trades and regimes positionally; mismatched lengths fail closed."""
    trade_list = list(trades)
    regime_list = list(regimes)
    if len(trade_list) != len(regime_list):
        raise ValueError("trades and regimes must have equal length")

    groups: dict[str, list[BacktestTrade]] = {}
    for trade, regime in zip(trade_list, regime_list):
        name = regime.value if isinstance(regime, Regime) else str(regime).strip() or "UNKNOWN"
        groups.setdefault(name, []).append(trade)

    rows = []
    for name, items in groups.items():
        wins = sum(t.net_pnl > 0 for t in items)
        losses = sum(t.net_pnl < 0 for t in items)
        net = sum(t.net_pnl for t in items)
        rows.append(RegimeAttribution(name, len(items), wins, losses, net, net / len(items), wins / len(items) * 100))
    return tuple(sorted(rows, key=lambda row: row.regime))
