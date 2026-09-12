"""Deterministic paper-trading engine; never routes orders to a broker."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
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

    def submit(self, order: PaperOrder) -> None:
        if self.open_order is not None:
            raise RuntimeError("paper engine already has an open position")
        if order.timestamp.tzinfo is None or order.timestamp.utcoffset() is None:
            raise ValueError("order timestamp must be timezone-aware")
        if order.direction not in (Direction.BUY, Direction.SELL):
            raise ValueError("order direction must be BUY or SELL")
        if not all(isfinite(float(x)) and x > 0 for x in (order.entry, order.sl, order.volume)):
            raise ValueError("order prices and volume must be positive and finite")
        if order.direction is Direction.BUY and order.sl >= order.entry:
            raise ValueError("BUY stop must be below entry")
        if order.direction is Direction.SELL and order.sl <= order.entry:
            raise ValueError("SELL stop must be above entry")
        modeled_loss = abs(order.entry - order.sl) * order.volume
        self.ledger.require_can_open(order.timestamp.date(), modeled_loss)
        if not self.risk_state.can_open():
            raise RuntimeError("risk state blocks new paper order")
        self.open_order = order

    def close(self, exit_price: float, timestamp: datetime, reason: str = "MANUAL") -> PaperFill:
        order = self.open_order
        if order is None:
            raise RuntimeError("no open paper position")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("fill timestamp must be timezone-aware")
        if not isfinite(float(exit_price)) or exit_price <= 0:
            raise ValueError("exit price must be positive and finite")
        pnl_per_unit = (exit_price - order.entry) if order.direction is Direction.BUY else (order.entry - exit_price)
        pnl = pnl_per_unit * order.volume
        fill = PaperFill(order, float(exit_price), pnl, timestamp, reason)
        self.fills.append(fill)
        self.ledger.record(timestamp.date(), pnl)
        self.risk_state.record_result(pnl)
        self.open_order = None
        return fill
