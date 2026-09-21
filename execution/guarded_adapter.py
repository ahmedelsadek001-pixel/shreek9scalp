"""Fail-closed execution adapter boundary for SHREEK V5.3."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, cast
from execution.execution_gate import ExecutionGateDecision, is_gate_issued
from execution.idempotency import IdempotencyLedger
from execution.reconciliation import OrderIntent

T=TypeVar("T")
LegacyExecutor=Callable[[],T]
IntentExecutor=Callable[[OrderIntent],T]
Executor=Callable[...,T]

@dataclass(frozen=True)
class GuardedExecutionResult(Generic[T]):
    executed: bool
    result: T|None
    reasons: tuple[str,...]

class GuardedExecutionAdapter(Generic[T]):
    """Invoke transport only after gate approval and duplicate reservation."""

    def __init__(self,executor:Executor,ledger:IdempotencyLedger|None=None)->None:
        if not callable(executor): raise TypeError("executor must be callable")
        if ledger is not None and not isinstance(ledger,IdempotencyLedger):
            raise TypeError("ledger must be an IdempotencyLedger")
        self._executor=executor
        self._ledger=ledger

    @staticmethod
    def _validate_decision(decision:ExecutionGateDecision)->tuple[str,...]|None:
        if not isinstance(decision,ExecutionGateDecision) or not is_gate_issued(decision):
            return ("execution gate decision not issued by execution gate",)
        if type(decision.allowed) is not bool: return ("execution gate decision malformed",)
        if not isinstance(decision.reasons,tuple) or any(not isinstance(x,str) for x in decision.reasons):
            return ("execution gate reasons malformed",)
        if decision.allowed and decision.reasons: return ("execution gate decision internally inconsistent",)
        if not decision.allowed: return decision.reasons or ("execution gate rejected without reason",)
        return None

    def execute(self,decision:ExecutionGateDecision)->GuardedExecutionResult[T]:
        reasons=self._validate_decision(decision)
        if reasons is not None: return GuardedExecutionResult(False,None,reasons)
        try: result=cast(LegacyExecutor[T],self._executor)()
        except Exception as exc: return GuardedExecutionResult(False,None,(f"downstream execution failed: {exc}",))
        return GuardedExecutionResult(True,result,())

    def execute_intent(self,decision:ExecutionGateDecision,intent:OrderIntent)->GuardedExecutionResult[T]:
        reasons=self._validate_decision(decision)
        if reasons is not None: return GuardedExecutionResult(False,None,reasons)
        if not isinstance(intent,OrderIntent): return GuardedExecutionResult(False,None,("order intent malformed",))
        if not isinstance(intent.order_id,str) or not intent.order_id.strip(): return GuardedExecutionResult(False,None,("order intent identity missing",))
        if not isinstance(intent.symbol,str) or not intent.symbol.strip(): return GuardedExecutionResult(False,None,("order intent symbol missing",))
        if self._ledger is not None:
            try: self._ledger.begin(intent)
            except ValueError as exc: return GuardedExecutionResult(False,None,(f"idempotency rejected: {exc}",))
        try:
            result=cast(IntentExecutor[T],self._executor)(intent)
        except Exception as exc:
            if self._ledger is not None:
                try: self._ledger.mark_transport_failure(intent.order_id)
                except ValueError: pass
            return GuardedExecutionResult(False,None,(f"downstream execution failed: {exc}",))
        # Successful function return is only transport completion. The caller
        # must finish ACCEPTED/REJECTED from explicit broker acknowledgement.
        return GuardedExecutionResult(True,result,())
