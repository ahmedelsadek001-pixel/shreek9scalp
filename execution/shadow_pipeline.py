"""Shadow validation bridge for the V5.1 paper-trade pipeline.

The bridge mirrors an accepted paper order into an OrderIntent and requires a
matching observed report. It has no broker transport capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.enums import Direction
from execution.reconciliation import ExecutionReport, OrderIntent, ReconciliationResult
from execution.shadow import ShadowExecution
from paper_trading.engine import PaperFill, PaperOrder


@dataclass(frozen=True)
class ShadowValidation:
    order_id: str
    reconciled: bool
    reasons: tuple[str, ...]


class PaperShadowBridge:
    """Connect paper orders to shadow reconciliation without live execution."""

    def __init__(self, shadow: Optional[ShadowExecution] = None) -> None:
        self.shadow = shadow or ShadowExecution()

    def register_paper_order(self, order_id: str, order: PaperOrder) -> OrderIntent:
        if not order_id:
            raise ValueError("order_id is required")
        if not isinstance(order, PaperOrder):
            raise TypeError("order must be PaperOrder")
        intent = OrderIntent(order_id, order.symbol, order.direction, order.volume, order.entry)
        self.shadow.submit_intent(intent)
        return intent

    def reconcile_paper_fill(self, order_id: str, fill: PaperFill) -> ShadowValidation:
        if not isinstance(fill, PaperFill):
            raise TypeError("fill must be PaperFill")
        report = ExecutionReport(
            order_id=order_id,
            symbol=fill.order.symbol,
            direction=fill.order.direction,
            volume=fill.order.volume,
            fill_price=fill.order.entry,
        )
        result: ReconciliationResult = self.shadow.observe(report)
        return ShadowValidation(order_id, result.matched, result.reasons)
