"""Broker-neutral shadow execution boundary for SHREEK V5.1.

This adapter records intended submissions and observed reports for validation.
It deliberately exposes no broker order-send operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from execution.reconciliation import ExecutionReport, OrderIntent, ReconciliationResult, reconcile_execution


@dataclass(frozen=True)
class ShadowSubmission:
    intent: OrderIntent


class ShadowExecution:
    """Deterministic in-memory shadow adapter; never routes to a broker."""

    def __init__(self) -> None:
        self._submissions: dict[str, ShadowSubmission] = {}
        self._reports: dict[str, ExecutionReport] = {}

    def submit_intent(self, intent: OrderIntent) -> ShadowSubmission:
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be OrderIntent")
        if not intent.order_id:
            raise ValueError("order_id is required")
        if intent.order_id in self._submissions:
            raise ValueError("duplicate order identity")
        self._submissions[intent.order_id] = ShadowSubmission(intent)
        return self._submissions[intent.order_id]

    def observe(self, report: ExecutionReport) -> ReconciliationResult:
        if not isinstance(report, ExecutionReport):
            raise TypeError("report must be ExecutionReport")
        if report.order_id not in self._submissions:
            return ReconciliationResult(False, ("unknown order identity",))
        if report.order_id in self._reports:
            return ReconciliationResult(False, ("duplicate execution report",))
        result = reconcile_execution(self._submissions[report.order_id].intent, report)
        if result.matched:
            self._reports[report.order_id] = report
        return result

    def pending_order_ids(self) -> tuple[str, ...]:
        return tuple(order_id for order_id in self._submissions if order_id not in self._reports)

    def submissions(self) -> Sequence[ShadowSubmission]:
        return tuple(self._submissions.values())
