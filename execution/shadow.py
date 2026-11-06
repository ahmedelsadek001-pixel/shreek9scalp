"""Broker-neutral shadow execution boundary for SHREEK V5.1.

This adapter records intended submissions and observed reports for validation.
It deliberately exposes no broker order-send operation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Sequence

from execution.reconciliation import ExecutionReport, OrderIntent, ReconciliationResult, reconcile_execution


@dataclass(frozen=True)
class ShadowSubmission:
    intent: OrderIntent


def _snapshot_intent(intent: OrderIntent) -> OrderIntent:
    """Copy caller-owned intent fields before retaining or exposing them."""
    return OrderIntent(
        deepcopy(intent.order_id),
        deepcopy(intent.symbol),
        deepcopy(intent.direction),
        deepcopy(intent.volume),
        deepcopy(intent.expected_price),
    )


def _snapshot_report(report: ExecutionReport) -> ExecutionReport:
    """Retain the exact report values that passed reconciliation."""
    return ExecutionReport(
        deepcopy(report.order_id),
        deepcopy(report.symbol),
        deepcopy(report.direction),
        deepcopy(report.volume),
        deepcopy(report.fill_price),
    )


def _public_submission(submission: ShadowSubmission) -> ShadowSubmission:
    """Return a detached snapshot instead of exposing internal recovery state."""
    return ShadowSubmission(_snapshot_intent(submission.intent))


class ShadowExecution:
    """Deterministic in-memory shadow adapter; never routes to a broker."""

    def __init__(self) -> None:
        self._submissions: dict[str, ShadowSubmission] = {}
        self._reports: dict[str, ExecutionReport] = {}
        self._revision = 0

    @property
    def state_revision(self) -> int:
        """Return the monotonic revision used to expire recovery approvals."""
        return self._revision

    def submit_intent(self, intent: OrderIntent) -> ShadowSubmission:
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be OrderIntent")
        if not intent.order_id:
            raise ValueError("order_id is required")
        if intent.order_id in self._submissions:
            raise ValueError("duplicate order identity")
        stored = ShadowSubmission(_snapshot_intent(intent))
        self._submissions[intent.order_id] = stored
        self._revision += 1
        return _public_submission(stored)

    def observe(self, report: ExecutionReport) -> ReconciliationResult:
        if not isinstance(report, ExecutionReport):
            raise TypeError("report must be ExecutionReport")
        if report.order_id not in self._submissions:
            return ReconciliationResult(False, ("unknown order identity",))
        if report.order_id in self._reports:
            return ReconciliationResult(False, ("duplicate execution report",))
        result = reconcile_execution(self._submissions[report.order_id].intent, report)
        if result.matched:
            self._reports[report.order_id] = _snapshot_report(report)
            self._revision += 1
        return result

    def pending_order_ids(self) -> tuple[str, ...]:
        return tuple(order_id for order_id in self._submissions if order_id not in self._reports)

    def submissions(self) -> Sequence[ShadowSubmission]:
        return tuple(_public_submission(item) for item in self._submissions.values())
