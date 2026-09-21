"""Idempotent execution-intent ledger for SHREEK V5.3.

The ledger prevents duplicate transport attempts after an intent reaches an
uncertain/accepted terminal boundary. It contains no broker connectivity.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from execution.reconciliation import OrderIntent


class SubmissionState(Enum):
    NEW = "new"
    IN_FLIGHT = "in_flight"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SubmissionRecord:
    order_id: str
    state: SubmissionState
    attempts: int


class IdempotencyLedger:
    def __init__(self) -> None:
        self._records: dict[str, SubmissionRecord] = {}

    @staticmethod
    def _identity(intent: OrderIntent) -> str:
        if not isinstance(intent, OrderIntent):
            raise ValueError("intent must be an OrderIntent")
        if not isinstance(intent.order_id, str) or not intent.order_id.strip():
            raise ValueError("order intent identity is required")
        return intent.order_id.strip()

    def begin(self, intent: OrderIntent) -> SubmissionRecord:
        """Reserve one transport attempt or fail closed on unsafe replay."""
        order_id = self._identity(intent)
        current = self._records.get(order_id)
        if current is not None:
            if current.state in (SubmissionState.IN_FLIGHT, SubmissionState.ACCEPTED, SubmissionState.UNKNOWN):
                raise ValueError(f"order {order_id} cannot be resubmitted from {current.state.value}")
            if current.state is SubmissionState.REJECTED:
                raise ValueError(f"order {order_id} requires a new identity after rejection")
        record = SubmissionRecord(order_id, SubmissionState.IN_FLIGHT, 1)
        self._records[order_id] = record
        return record

    def finish(self, order_id: str, state: SubmissionState) -> SubmissionRecord:
        """Close an in-flight attempt with an explicit broker outcome."""
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id is required")
        if not isinstance(state, SubmissionState) or state in (SubmissionState.NEW, SubmissionState.IN_FLIGHT):
            raise ValueError("finish requires accepted, rejected, or unknown state")
        current = self._records.get(order_id.strip())
        if current is None or current.state is not SubmissionState.IN_FLIGHT:
            raise ValueError("order has no in-flight submission")
        record = SubmissionRecord(current.order_id, state, current.attempts)
        self._records[current.order_id] = record
        return record

    def mark_transport_failure(self, order_id: str) -> SubmissionRecord:
        """Network/timeout failures are UNKNOWN, never automatically retryable."""
        return self.finish(order_id, SubmissionState.UNKNOWN)

    def get(self, order_id: str) -> SubmissionRecord | None:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id is required")
        return self._records.get(order_id.strip())

    def reconcile_unknown(self, order_id: str, *, broker_order_exists: bool) -> SubmissionRecord:
        """Resolve UNKNOWN only from explicit broker reconciliation evidence."""
        if type(broker_order_exists) is not bool:
            raise ValueError("broker_order_exists must be a bool")
        current = self.get(order_id)
        if current is None or current.state is not SubmissionState.UNKNOWN:
            raise ValueError("order is not awaiting reconciliation")
        state = SubmissionState.ACCEPTED if broker_order_exists else SubmissionState.REJECTED
        record = SubmissionRecord(current.order_id, state, current.attempts)
        self._records[current.order_id] = record
        return record
