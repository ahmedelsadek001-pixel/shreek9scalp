"""Deterministic paper-trading engine; never routes orders to a broker."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from threading import Lock
from typing import Optional

from core.enums import Direction
from risk.daily_risk_ledger import DailyRiskLedger
from risk.risk_state import RiskStateMachine


@dataclass(frozen=True)
class PaperOrder:
    symbol: str
    direction: Direction
    entry: float
    sl: float
    volume: float
    timestamp: datetime


@dataclass(frozen=True)
class PaperFill:
    order: PaperOrder
    exit_price: float
    pnl: float
    timestamp: datetime
    reason: str


class PaperTradingEngine:
    """Single-position deterministic simulator with fail-closed risk gates."""

    def __init__(self, starting_equity: float = 10000.0, max_daily_loss_pct: float = 0.05,
                 risk_state: Optional[RiskStateMachine] = None) -> None:
        self.ledger = DailyRiskLedger(starting_equity, max_daily_loss_pct)
        self.risk_state = risk_state or RiskStateMachine()
        self.open_order: Optional[PaperOrder] = None
        self.fills: list[PaperFill] = []
        self._position_lock = Lock()

    def submit(self, order: PaperOrder) -> None:
        """Atomically validate and open the single paper position."""
        with self._position_lock:
            if self.open_order is not None:
                raise RuntimeError("paper engine already has an open position")
            if order.timestamp.tzinfo is None or order.timestamp.utcoffset() is None:
                raise ValueError("order timestamp must be timezone-aware")
            if order.direction not in (Direction.BUY, Direction.SELL):
                raise ValueError("order direction must be BUY or SELL")
            try:
                entry, sl, volume = float(order.entry), float(order.sl), float(order.volume)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("order prices and volume must be positive and finite") from exc
            if not all(isfinite(value) and value > 0 for value in (entry, sl, volume)):
                raise ValueError("order prices and volume must be positive and finite")
            if order.direction is Direction.BUY and sl >= entry:
                raise ValueError("BUY stop must be below entry")
            if order.direction is Direction.SELL and sl <= entry:
                raise ValueError("SELL stop must be above entry")
            modeled_loss = abs(entry - sl) * volume
            if not isfinite(modeled_loss) or modeled_loss <= 0:
                raise ValueError("modeled loss must be positive and finite")
            normalized_order = PaperOrder(order.symbol, order.direction, entry, sl, volume, order.timestamp)
            self.ledger.require_can_open(order.timestamp.date(), modeled_loss)
            if not self.risk_state.can_open():
                raise RuntimeError("risk state blocks new paper order")
            self.open_order = normalized_order

    def close(self, exit_price: float, timestamp: datetime, reason: str = "MANUAL") -> PaperFill:
        """Atomically close the current paper position and record its result."""
        with self._position_lock:
            order = self.open_order
            if order is None:
                raise RuntimeError("no open paper position")
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("fill timestamp must be timezone-aware")
            try:
                normalized_exit = float(exit_price)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("exit price must be positive and finite") from exc
            if not isfinite(normalized_exit) or normalized_exit <= 0:
                raise ValueError("exit price must be positive and finite")
            pnl_per_unit = (normalized_exit - order.entry) if order.direction is Direction.BUY else (order.entry - normalized_exit)
            pnl = pnl_per_unit * order.volume
            if not isfinite(pnl):
                raise ValueError("calculated PnL must be finite")
            fill = PaperFill(order, normalized_exit, pnl, timestamp, reason)
            self.ledger.record(timestamp.date(), pnl)
            self.risk_state.record_result(pnl)
            self.fills.append(fill)
            self.open_order = None
            return fill
