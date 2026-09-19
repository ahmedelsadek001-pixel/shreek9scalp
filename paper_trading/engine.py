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
            if not isinstance(order, PaperOrder):
                raise ValueError("order must be a PaperOrder")
            if not isinstance(order.symbol, str) or not order.symbol.strip():
                raise ValueError("order symbol must be a non-empty string")
            if not isinstance(order.timestamp, datetime):
                raise ValueError("order timestamp must be a datetime")
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
            normalized_order = PaperOrder(order.symbol.strip(), order.direction, entry, sl, volume, order.timestamp)
            self.ledger.require_can_open(order.timestamp.date(), modeled_loss)
            if not self.risk_state.can_open():
                raise RuntimeError("risk state blocks new paper order")
            self.open_order = normalized_order

    def close(self, exit_price: float, timestamp: datetime, reason: str = "MANUAL") -> PaperFill:
        """Close a position and atomically record both risk views or roll back."""
        with self._position_lock:
            order = self.open_order
            if order is None:
                raise RuntimeError("no open paper position")
            if not isinstance(timestamp, datetime):
                raise ValueError("fill timestamp must be a datetime")
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("fill timestamp must be timezone-aware")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("close reason must be a non-empty string")
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

            day = timestamp.date()
            previous_realized = self.ledger._realized_by_day.get(day)
            previous_state = self.risk_state.state
            previous_losses = self.risk_state.consecutive_losses
            fill = PaperFill(order, normalized_exit, pnl, timestamp, reason.strip())
            try:
                self.ledger.record(day, pnl)
                self.risk_state.record_result(pnl)
            except Exception:
                if previous_realized is None:
                    self.ledger._realized_by_day.pop(day, None)
                else:
                    self.ledger._realized_by_day[day] = previous_realized
                self.risk_state.state = previous_state
                self.risk_state.consecutive_losses = previous_losses
                raise
            self.fills.append(fill)
            self.open_order = None
            return fill
