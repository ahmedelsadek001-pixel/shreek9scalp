"""Deterministic paper-trading state machine.

This module deliberately does not connect to MT5 or any broker. It accepts
already-admitted execution levels and records simulated orders only after the
risk and robustness gates have passed.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class PaperOrder:
    symbol: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    volume: float
    reason: str = ""

    def validate(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        values = (self.entry, self.stop_loss, self.take_profit, self.volume)
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("order values must be finite")
        if self.entry <= 0 or self.stop_loss <= 0 or self.take_profit <= 0 or self.volume <= 0:
            raise ValueError("order values must be positive")
        if self.direction == "LONG" and not (self.stop_loss < self.entry < self.take_profit):
            raise ValueError("invalid LONG order geometry")
        if self.direction == "SHORT" and not (self.take_profit < self.entry < self.stop_loss):
            raise ValueError("invalid SHORT order geometry")


@dataclass(frozen=True)
class PaperFill:
    order: PaperOrder
    exit_price: Optional[float]
    exit_reason: Optional[str]
    realized_pnl: float


class PaperTradingEngine:
    """One-position-at-a-time paper engine with explicit admission boundaries."""

    def __init__(self, starting_equity: float = 10000.0) -> None:
        if not isfinite(starting_equity) or starting_equity <= 0:
            raise ValueError("starting equity must be positive and finite")
        self.equity = float(starting_equity)
        self.open_order: Optional[PaperOrder] = None
        self.fills: list[PaperFill] = []

    def submit(self, order: PaperOrder, admitted: bool, robustness_passed: bool = False) -> bool:
        """Open only when both signal admission and robustness validation pass."""
        order.validate()
        if not admitted or not robustness_passed:
            return False
        if self.open_order is not None:
            raise RuntimeError("a paper position is already open")
        self.open_order = order
        return True

    def close(self, price: float, reason: str) -> PaperFill:
        """Close the current paper position and update equity deterministically."""
        if self.open_order is None:
            raise RuntimeError("no paper position is open")
        if not isfinite(price) or price <= 0:
            raise ValueError("exit price must be positive and finite")
        if not reason.strip():
            raise ValueError("exit reason is required")
        order = self.open_order
        pnl_per_unit = price - order.entry if order.direction == "LONG" else order.entry - price
        pnl = pnl_per_unit * order.volume
        fill = PaperFill(order, float(price), reason, pnl)
        self.equity += pnl
        self.open_order = None
        self.fills.append(fill)
        return fill
