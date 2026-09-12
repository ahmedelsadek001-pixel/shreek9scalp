"""Fail-closed execution adapter boundary for SHREEK V5.3.

The boundary separates safety admission from transport. A downstream adapter
may be called only after an explicit successful ExecutionGateDecision issued by
the execution gate. This module itself has no broker/network authority and is
safe to use for tests, shadow execution, or future broker adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from execution.execution_gate import ExecutionGateDecision, is_gate_issued


T = TypeVar("T")


@dataclass(frozen=True)
class GuardedExecutionResult(Generic[T]):
    """Result of a gated adapter invocation."""

    executed: bool
    result: T | None
    reasons: tuple[str, ...]


class GuardedExecutionAdapter(Generic[T]):
    """Invoke a downstream executor only after a valid gate-issued decision.

    The executor is deliberately injected as a callable. This keeps the safety
    boundary broker-agnostic while making bypass behavior directly testable.
    """

    def __init__(self, executor: Callable[[], T]) -> None:
        if not callable(executor):
            raise TypeError("executor must be callable")
        self._executor = executor

    def execute(self, decision: ExecutionGateDecision) -> GuardedExecutionResult[T]:
        """Execute only when the decision is gate-issued, valid, and allowed."""
        if not isinstance(decision, ExecutionGateDecision) or not is_gate_issued(decision):
            return GuardedExecutionResult(False, None, ("execution gate decision not issued by execution gate",))
        if type(decision.allowed) is not bool:
            return GuardedExecutionResult(False, None, ("execution gate decision malformed",))
        if not isinstance(decision.reasons, tuple) or any(not isinstance(item, str) for item in decision.reasons):
            return GuardedExecutionResult(False, None, ("execution gate reasons malformed",))
        if decision.allowed and decision.reasons:
            return GuardedExecutionResult(False, None, ("execution gate decision internally inconsistent",))
        if not decision.allowed:
            reasons = decision.reasons or ("execution gate rejected without reason",)
            return GuardedExecutionResult(False, None, reasons)
        try:
            result = self._executor()
        except Exception as exc:
            return GuardedExecutionResult(False, None, (f"downstream execution failed: {exc}",))
        return GuardedExecutionResult(True, result, ())
