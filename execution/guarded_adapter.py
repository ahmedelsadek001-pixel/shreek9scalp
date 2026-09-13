"""Fail-closed execution adapter boundary for SHREEK V5.3.

The boundary separates safety admission from transport. A downstream adapter
may be called only after an explicit successful ExecutionGateDecision issued by
the execution gate. Intent-aware execution additionally binds the admitted
order identity to the downstream transport call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from execution.execution_gate import ExecutionGateDecision, is_gate_issued
from execution.reconciliation import OrderIntent


T = TypeVar("T")


@dataclass(frozen=True)
class GuardedExecutionResult(Generic[T]):
    """Result of a gated adapter invocation."""

    executed: bool
    result: T | None
    reasons: tuple[str, ...]


class GuardedExecutionAdapter(Generic[T]):
    """Invoke a downstream executor only after a valid gate-issued decision.

    The legacy ``execute`` method remains broker-agnostic and is retained for
    compatibility. New transport paths must use ``execute_intent`` so the
    immutable OrderIntent identity is passed to the executor as part of the
    guarded boundary rather than being handled outside it.
    """

    def __init__(self, executor: Callable[[], T]) -> None:
        if not callable(executor):
            raise TypeError("executor must be callable")
        self._executor = executor

    @staticmethod
    def _validate_decision(decision: ExecutionGateDecision) -> tuple[str, ...] | None:
        if not isinstance(decision, ExecutionGateDecision) or not is_gate_issued(decision):
            return ("execution gate decision not issued by execution gate",)
        if type(decision.allowed) is not bool:
            return ("execution gate decision malformed",)
        if not isinstance(decision.reasons, tuple) or any(not isinstance(item, str) for item in decision.reasons):
            return ("execution gate reasons malformed",)
        if decision.allowed and decision.reasons:
            return ("execution gate decision internally inconsistent",)
        if not decision.allowed:
            return decision.reasons or ("execution gate rejected without reason",)
        return None

    def execute(self, decision: ExecutionGateDecision) -> GuardedExecutionResult[T]:
        """Execute only when the decision is gate-issued, valid, and allowed."""
        reasons = self._validate_decision(decision)
        if reasons is not None:
            return GuardedExecutionResult(False, None, reasons)
        try:
            result = self._executor()
        except Exception as exc:
            return GuardedExecutionResult(False, None, (f"downstream execution failed: {exc}",))
        return GuardedExecutionResult(True, result, ())

    def execute_intent(self, decision: ExecutionGateDecision, intent: OrderIntent) -> GuardedExecutionResult[T]:
        """Execute a gate-approved immutable order intent through one boundary.

        The adapter validates identity-bearing intent fields before transport.
        The injected executor receives the exact intent object, preventing a
        transport layer from silently substituting a different order identity.
        """
        reasons = self._validate_decision(decision)
        if reasons is not None:
            return GuardedExecutionResult(False, None, reasons)
        if not isinstance(intent, OrderIntent):
            return GuardedExecutionResult(False, None, ("order intent malformed",))
        if not isinstance(intent.order_id, str) or not intent.order_id.strip():
            return GuardedExecutionResult(False, None, ("order intent identity missing",))
        if not isinstance(intent.symbol, str) or not intent.symbol.strip():
            return GuardedExecutionResult(False, None, ("order intent symbol missing",))
        try:
            result = self._executor(intent)  # type: ignore[call-arg]
        except Exception as exc:
            return GuardedExecutionResult(False, None, (f"downstream execution failed: {exc}",))
        return GuardedExecutionResult(True, result, ())
