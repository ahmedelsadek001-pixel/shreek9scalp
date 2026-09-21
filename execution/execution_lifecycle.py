"""Fail-closed execution lifecycle coordination for SHREEK V5.3."""
from __future__ import annotations
from dataclasses import dataclass
from execution.broker_outcome import BrokerOutcome, BrokerOutcomeDecision
from execution.idempotency import IdempotencyLedger, SubmissionState
from execution.reconciliation import ExecutionReport, OrderIntent, ReconciliationResult, reconcile_execution

@dataclass(frozen=True)
class LifecycleDecision:
    safe: bool
    state: SubmissionState
    reasons: tuple[str,...]

class ExecutionLifecycleCoordinator:
    """Bind broker outcome, idempotency and reconciliation into one state machine."""

    def __init__(self,ledger:IdempotencyLedger)->None:
        if not isinstance(ledger,IdempotencyLedger): raise TypeError("ledger must be IdempotencyLedger")
        self.ledger=ledger

    def apply_outcome(self,intent:OrderIntent,outcome:BrokerOutcomeDecision)->LifecycleDecision:
        if not isinstance(intent,OrderIntent): raise ValueError("intent must be OrderIntent")
        if not isinstance(outcome,BrokerOutcomeDecision): raise ValueError("outcome must be BrokerOutcomeDecision")
        current=self.ledger.get(intent.order_id)
        if current is None or current.state is not SubmissionState.IN_FLIGHT:
            raise ValueError("intent has no in-flight submission")
        if outcome.outcome is BrokerOutcome.ACCEPTED:
            record=self.ledger.finish(intent.order_id,SubmissionState.ACCEPTED)
            return LifecycleDecision(True,record.state,())
        if outcome.outcome is BrokerOutcome.UNKNOWN:
            record=self.ledger.finish(intent.order_id,SubmissionState.UNKNOWN)
            return LifecycleDecision(False,record.state,(outcome.reason,))
        record=self.ledger.finish(intent.order_id,SubmissionState.REJECTED)
        # Even an explicitly retryable rejection requires a fresh order identity.
        return LifecycleDecision(False,record.state,(outcome.reason,))

    def reconcile(self,intent:OrderIntent,report:ExecutionReport,*,price_tolerance:float=0.0,volume_tolerance:float=0.0)->ReconciliationResult:
        if not isinstance(intent,OrderIntent): raise ValueError("intent must be OrderIntent")
        current=self.ledger.get(intent.order_id)
        if current is None or current.state not in (SubmissionState.ACCEPTED,SubmissionState.UNKNOWN):
            raise ValueError("intent is not eligible for reconciliation")
        result=reconcile_execution(intent,report,price_tolerance=price_tolerance,volume_tolerance=volume_tolerance)
        if current.state is SubmissionState.UNKNOWN:
            self.ledger.reconcile_unknown(intent.order_id,broker_order_exists=result.matched)
        return result
