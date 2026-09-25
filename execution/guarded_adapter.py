"""Fail-closed execution adapter boundary for SHREEK V5.3."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Callable, Generic, TypeVar, cast
from core.enums import Direction
from execution.execution_gate import ExecutionGateDecision, is_gate_issued
from execution.idempotency import IdempotencyLedger
from execution.reconciliation import OrderIntent
from execution.quote_safety import QuoteSafetyDecision, is_quote_issued

T=TypeVar("T")
IntentExecutor=Callable[[OrderIntent],T]
Executor=Callable[...,T]


def utc_now() -> datetime:
    """Use wall time again at submission; a quote can expire after evaluation."""
    return datetime.now(timezone.utc)

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
        if decision.admitted_symbol is None or decision.admitted_volume is None:
            return ("execution requires evaluated environment",)
        return None

    def execute(self,decision:ExecutionGateDecision)->GuardedExecutionResult[T]:
        """Retain legacy signature while refusing transport without an intent."""
        reasons=self._validate_decision(decision)
        if reasons is not None: return GuardedExecutionResult(False,None,reasons)
        return GuardedExecutionResult(False,None,("unscoped execution disabled",))

    def execute_intent(self,decision:ExecutionGateDecision,intent:OrderIntent,quote_safety:QuoteSafetyDecision|None=None)->GuardedExecutionResult[T]:
        reasons=self._validate_decision(decision)
        if reasons is not None: return GuardedExecutionResult(False,None,reasons)
        if not isinstance(intent,OrderIntent): return GuardedExecutionResult(False,None,("order intent malformed",))
        if not isinstance(intent.order_id,str) or not intent.order_id.strip(): return GuardedExecutionResult(False,None,("order intent identity missing",))
        if not isinstance(intent.symbol,str) or not intent.symbol.strip(): return GuardedExecutionResult(False,None,("order intent symbol missing",))
        if intent.direction not in (Direction.BUY, Direction.SELL) or not isinstance(intent.direction,Direction):
            return GuardedExecutionResult(False,None,("order intent direction invalid",))
        if (type(intent.volume) not in (int,float) or not isfinite(intent.volume)
                or intent.volume <= 0 or type(intent.expected_price) not in (int,float)
                or not isfinite(intent.expected_price) or intent.expected_price <= 0):
            return GuardedExecutionResult(False,None,("order intent economics invalid",))
        if decision.admitted_symbol != intent.symbol or decision.admitted_volume != intent.volume:
            return GuardedExecutionResult(False,None,("evaluated environment does not match intent",))
        if quote_safety is None:
            return GuardedExecutionResult(False,None,("quote safety decision required",))
        if not isinstance(quote_safety,QuoteSafetyDecision) or type(quote_safety.allowed) is not bool or not isinstance(quote_safety.reason,str):
            return GuardedExecutionResult(False,None,("quote safety decision malformed",))
        if not quote_safety.allowed:
            return GuardedExecutionResult(False,None,(f"quote safety: {quote_safety.reason}",))
        if not is_quote_issued(quote_safety):
            return GuardedExecutionResult(False,None,("quote safety decision not issued by quote gate",))
        if quote_safety.intended_price != intent.expected_price:
            return GuardedExecutionResult(False,None,("quote safety price does not match intent",))
        now = utc_now()
        if (quote_safety.quote_time is None or quote_safety.evaluated_at is None
                or quote_safety.max_age_seconds is None):
            return GuardedExecutionResult(False,None,("quote timing evidence missing",))
        if (now - quote_safety.evaluated_at).total_seconds() < 0:
            return GuardedExecutionResult(False,None,("quote evaluated in the future",))
        if (now - quote_safety.quote_time).total_seconds() > quote_safety.max_age_seconds:
            return GuardedExecutionResult(False,None,("quote expired before submission",))
        if self._ledger is None:
            return GuardedExecutionResult(False,None,("idempotency ledger required",))
        try: self._ledger.begin(intent)
        except ValueError as exc: return GuardedExecutionResult(False,None,(f"idempotency rejected: {exc}",))
        try:
            result=cast(IntentExecutor[T],self._executor)(intent)
        except Exception as exc:
            try: self._ledger.mark_transport_failure(intent.order_id)
            except ValueError: pass
            return GuardedExecutionResult(False,None,(f"downstream execution failed: {exc}",))
        # Successful function return is only transport completion. The caller
        # must finish ACCEPTED/REJECTED from explicit broker acknowledgement.
        return GuardedExecutionResult(True,result,())

    def execute_intent_strict(
        self,
        decision: ExecutionGateDecision,
        intent: OrderIntent,
        quote_safety: QuoteSafetyDecision,
    ) -> GuardedExecutionResult[T]:
        """Submit an intent only with an explicit quote-safety decision.

        Both entry points now require an issued quote decision matching the
        intent price before the ledger or downstream transport is touched.
        """
        if quote_safety is None:
            return GuardedExecutionResult(False, None, ("quote safety decision required",))
        return self.execute_intent(decision, intent, quote_safety)
