"""Fail-closed execution adapter boundary for SHREEK V5.3.

The boundary separates safety admission from transport. A downstream adapter
may be called only after an explicit successful ExecutionGateDecision. This
module itself has no broker/network authority and is safe to use for tests,
shadow execution, or future broker adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from execution.execution_gate import ExecutionGateDecision


T = TypeVar("T")


@dataclass(frozen=True)
class GuardedExecutionResult(Generic[T]):
    """Result of a gated adapter invocation."""

    executed: bool
    result: T | None
    reasons: tuple[str, ...]


class GuardedExecutionAdapter(Generic[T]):
    """Invoke a downstream executor only after a valid allowed gate decision.

    The executor is deliberately injected as a callable. This keeps the safety
    boundary broker-agnostic while making bypass behavior directly testable.
    """

    def __init__(self, executor: Callable[[], T]) -> None:
        if not callable(executor):
            raise TypeError("executor must be callable")
        self._executor = executor

    def execute(self, decision: ExecutionGateDecision) -> GuardedExecutionResult[T]:
        """Execute only when the gate is structurally valid and allows it."""
        if not isinstance(decision, ExecutionGateDecision):
            return GuardedExecutionResult(False, None, ("execution gate decision malformed",))
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
