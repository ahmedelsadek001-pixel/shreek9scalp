"""Hierarchical fail-closed kill switches for SHREEK."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KillScope(str, Enum):
    TRADE = "trade"
    SESSION = "session"
    SYMBOL = "symbol"
    STRATEGY = "strategy"
    ENGINE = "engine"


@dataclass(frozen=True)
class KillSwitch:
    """Immutable hierarchical kill state; any active parent blocks trading."""

    trade: bool = False
    session: bool = False
    symbol: bool = False
    strategy: bool = False
    engine: bool = False

    def is_blocked(self) -> bool:
        return self.trade or self.session or self.symbol or self.strategy or self.engine

    def activate(self, scope: KillScope) -> "KillSwitch":
        values = {
            "trade": self.trade,
            "session": self.session,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "engine": self.engine,
        }
        values[scope.value] = True
        return KillSwitch(**values)

    def can_trade(self) -> bool:
        return not self.is_blocked()

    def require_live(self) -> None:
        if self.is_blocked():
            raise RuntimeError("kill switch active")
