"""Deterministic paper-trading state machine.

This module deliberately does not connect to MT5 or any broker. It accepts
already-admitted execution levels and records simulated orders only after the
risk and robustness gates have passed.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional

from journal.decision_journal import DecisionJournal, DecisionRecord


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

    @property
    def modeled_stop_risk(self) -> float:
        """Paper-model loss at stop before broker-specific contract conversion."""
        return abs(self.entry - self.stop_loss) * self.volume


@dataclass(frozen=True)
class PaperFill:
    order: PaperOrder
    exit_price: Optional[float]
    exit_reason: Optional[str]
    realized_pnl: float


class PaperTradingEngine:
    """One-position-at-a-time paper engine with explicit admission boundaries."""

    def __init__(self, starting_equity: float = 10000.0, journal: Optional[DecisionJournal] = None) -> None:
        if not isfinite(starting_equity) or starting_equity <= 0:
            raise ValueError("starting equity must be positive and finite")
        self.equity = float(starting_equity)
        self.open_order: Optional[PaperOrder] = None
        self.fills: list[PaperFill] = []
        self.journal = journal

    def _journal(self, order: PaperOrder, decision: str, reason: str) -> None:
        if self.journal is None:
            return
        self.journal.append(
            DecisionRecord.now(
                order.symbol,
                decision,
                order.direction,
                reason,
                fingerprint=None,
                score=None,
                setup_type=None,
                frame=None,
                entry=order.entry,
                sl=order.stop_loss,
                metadata={"volume": order.volume, "take_profit": order.take_profit},
            )
        )

    def submit(
        self,
        order: PaperOrder,
        admitted: bool,
        robustness_passed: bool = False,
        max_risk_usd: Optional[float] = None,
    ) -> bool:
        """Open only when admission, robustness and optional risk gates pass."""
        order.validate()
        if not admitted:
            self._journal(order, "PAPER_REJECT", "signal admission failed")
            return False
        if not robustness_passed:
            self._journal(order, "PAPER_REJECT", "robustness validation failed")
            return False
        if max_risk_usd is not None:
            if not isfinite(max_risk_usd) or max_risk_usd <= 0:
                raise ValueError("max_risk_usd must be positive and finite")
            if order.modeled_stop_risk > max_risk_usd:
                self._journal(order, "PAPER_REJECT", "modeled stop risk exceeds risk budget")
                return False
        if self.open_order is not None:
            raise RuntimeError("a paper position is already open")
        self.open_order = order
        self._journal(order, "PAPER_OPEN", order.reason or "paper order admitted")
        return True

    def submit_decision(
        self,
        order: PaperOrder,
        admission,
        robustness_report,
        max_risk_usd: Optional[float] = None,
    ) -> bool:
        """Consume typed gate results without allowing the engine to bypass them."""
        allowed = getattr(admission, "allowed", False)
        robust = getattr(robustness_report, "passed", False)
        return self.submit(
            order,
            admitted=bool(allowed),
            robustness_passed=bool(robust),
            max_risk_usd=max_risk_usd,
        )

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
        self._journal(order, "PAPER_CLOSE", reason)
        return fill
