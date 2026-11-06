"""Idempotent execution-intent ledger for SHREEK V5.3.

The ledger prevents duplicate transport attempts after an intent reaches an
uncertain/accepted terminal boundary. It contains no broker connectivity.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from math import isfinite

from core.enums import Direction
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
    intent_fingerprint: str | None = None


def validate_intent_fingerprint(value: object) -> None:
    """Allow an unbound legacy record, or a canonical SHA-256 binding."""
    if value is not None and (
        type(value) is not str or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("malformed original intent fingerprint")


def _number_ratio(value: object) -> tuple[int, int]:
    """Bind exact numeric values without rounding distinct large integers."""
    if type(value) not in (int, float):
        raise ValueError("order intent economics must be finite and positive")
    try:
        if not isfinite(value) or value <= 0:
            raise ValueError("order intent economics must be finite and positive")
    except OverflowError as exc:
        raise ValueError("order intent economics must be finite and positive") from exc
    return (value, 1) if type(value) is int else value.as_integer_ratio()


class IdempotencyLedger:
    def __init__(self) -> None:
        self._records: dict[str, SubmissionRecord] = {}

    def _validate_records(self) -> None:
        """Reject invalid reservations before reads or state transitions."""
        records = getattr(self, "_records", None)
        if not isinstance(records, dict):
            raise ValueError("ledger storage unavailable")
        for key, record in records.items():
            if type(key) is not str or not key.strip() or key != key.strip():
                raise ValueError("ledger contains malformed order identity")
            if not isinstance(record, SubmissionRecord):
                raise ValueError("ledger contains malformed submission record")
            if type(getattr(record, "order_id", None)) is not str or record.order_id != key:
                raise ValueError("ledger contains mismatched order identity")
            state = getattr(record, "state", None)
            if not isinstance(state, SubmissionState) or state is SubmissionState.NEW:
                raise ValueError("ledger contains malformed submission state")
            attempts = getattr(record, "attempts", None)
            if type(attempts) is not int or attempts < 1:
                raise ValueError("ledger contains malformed submission attempts")
            validate_intent_fingerprint(record.intent_fingerprint)

    def records(self) -> tuple[SubmissionRecord, ...]:
        """Return an immutable deterministic snapshot of ledger state."""
        self._validate_records()
        return tuple(self._records[key] for key in sorted(self._records))

    @classmethod
    def restore(cls, records: tuple[SubmissionRecord, ...]) -> "IdempotencyLedger":
        """Restore verified state without making any order retryable."""
        if not isinstance(records, tuple):
            raise TypeError("records must be a tuple")
        ledger = cls()
        for record in records:
            if not isinstance(record, SubmissionRecord):
                raise TypeError("records must contain SubmissionRecord values")
            if not isinstance(record.order_id, str) or not record.order_id.strip():
                raise ValueError("restored order identity is required")
            if not isinstance(record.state, SubmissionState) or record.state is SubmissionState.NEW:
                raise ValueError("restored submission state is invalid")
            if type(record.attempts) is not int or record.attempts < 1:
                raise ValueError("restored attempts must be a positive integer")
            key = record.order_id.strip()
            if key in ledger._records:
                raise ValueError("duplicate restored order identity")
            ledger._records[key] = SubmissionRecord(key, record.state, record.attempts, record.intent_fingerprint)
        ledger._validate_records()
        return ledger

    @staticmethod
    def _identity(intent: OrderIntent) -> str:
        if not isinstance(intent, OrderIntent):
            raise ValueError("intent must be an OrderIntent")
        if not isinstance(intent.order_id, str) or not intent.order_id.strip():
            raise ValueError("order intent identity is required")
        return intent.order_id.strip()

    @classmethod
    def fingerprint_intent(cls, intent: OrderIntent) -> str:
        """Return the canonical binding used for every intent-scoped artifact."""
        order_id = cls._identity(intent)
        if type(intent.symbol) is not str or not intent.symbol.strip():
            raise ValueError("order intent symbol is required")
        if not isinstance(intent.direction, Direction):
            raise ValueError("order intent direction must be Direction")
        # Typed non-execution directions remain representable for diagnostics;
        # reconciliation and admission independently require BUY or SELL.
        payload = {
            "version": 1, "order_id": order_id, "symbol": intent.symbol,
            "direction": intent.direction.value, "volume": _number_ratio(intent.volume),
            "expected_price": _number_ratio(intent.expected_price),
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def begin(self, intent: OrderIntent) -> SubmissionRecord:
        """Reserve one transport attempt or fail closed on unsafe replay."""
        order_id = self._identity(intent)
        self._validate_records()
        current = self._records.get(order_id)
        if current is not None:
            if current.state in (SubmissionState.NEW, SubmissionState.IN_FLIGHT,
                                 SubmissionState.ACCEPTED, SubmissionState.UNKNOWN):
                raise ValueError(f"order {order_id} cannot be resubmitted from {current.state.value}")
            if current.state is SubmissionState.REJECTED:
                raise ValueError(f"order {order_id} requires a new identity after rejection")
        record = SubmissionRecord(
            order_id, SubmissionState.IN_FLIGHT, 1,
            self.fingerprint_intent(intent),
        )
        self._records[order_id] = record
        return record

    def finish(self, order_id: str, state: SubmissionState) -> SubmissionRecord:
        """Close an in-flight attempt with an explicit broker outcome."""
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id is required")
        if not isinstance(state, SubmissionState) or state in (SubmissionState.NEW, SubmissionState.IN_FLIGHT):
            raise ValueError("finish requires accepted, rejected, or unknown state")
        self._validate_records()
        current = self._records.get(order_id.strip())
        if current is None or current.state is not SubmissionState.IN_FLIGHT:
            raise ValueError("order has no in-flight submission")
        record = SubmissionRecord(current.order_id, state, current.attempts, current.intent_fingerprint)
        self._records[current.order_id] = record
        return record

    def mark_transport_failure(self, order_id: str) -> SubmissionRecord:
        """Network/timeout failures are UNKNOWN, never automatically retryable."""
        return self.finish(order_id, SubmissionState.UNKNOWN)

    def get(self, order_id: str) -> SubmissionRecord | None:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id is required")
        self._validate_records()
        return self._records.get(order_id.strip())

    def get_for_intent(self, intent: OrderIntent) -> SubmissionRecord | None:
        """Require the original durable binding before intent-scoped decisions."""
        current = self.get(self._identity(intent))
        if current is None:
            return None
        if current.intent_fingerprint is None:
            raise ValueError("original intent binding unavailable")
        if current.intent_fingerprint != self.fingerprint_intent(intent):
            raise ValueError("intent does not match original reservation")
        return current

    def reconcile_unknown(self, order_id: str, *, broker_order_exists: bool) -> SubmissionRecord:
        """Resolve UNKNOWN only from explicit broker reconciliation evidence."""
        if type(broker_order_exists) is not bool:
            raise ValueError("broker_order_exists must be a bool")
        current = self.get(order_id)
        if current is None or current.state is not SubmissionState.UNKNOWN:
            raise ValueError("order is not awaiting reconciliation")
        state = SubmissionState.ACCEPTED if broker_order_exists else SubmissionState.REJECTED
        record = SubmissionRecord(current.order_id, state, current.attempts, current.intent_fingerprint)
        self._records[current.order_id] = record
        return record
