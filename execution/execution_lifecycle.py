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

    @staticmethod
    def _validate_outcome(outcome: BrokerOutcomeDecision) -> None:
        if not isinstance(outcome, BrokerOutcomeDecision):
            raise ValueError("outcome must be BrokerOutcomeDecision")
        if not isinstance(outcome.outcome, BrokerOutcome):
            raise ValueError("broker outcome is invalid")
        if type(outcome.retry_allowed) is not bool:
            raise ValueError("retry_allowed must be bool")
        if not isinstance(outcome.reason, str) or not outcome.reason.strip():
            raise ValueError("broker outcome reason is required")
        expected_retry = outcome.outcome is BrokerOutcome.REJECTED_RETRYABLE
        if outcome.retry_allowed is not expected_retry:
            raise ValueError("broker outcome retry policy is inconsistent")

    def apply_outcome(self,intent:OrderIntent,outcome:BrokerOutcomeDecision)->LifecycleDecision:
        if not isinstance(intent,OrderIntent): raise ValueError("intent must be OrderIntent")
        self._validate_outcome(outcome)
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
        if current.state is SubmissionState.UNKNOWN and result.matched:
            # An exact broker report proves presence. A mismatched report does
            # NOT prove absence and must leave UNKNOWN fail-closed.
            self.ledger.reconcile_unknown(intent.order_id,broker_order_exists=True)
        return result

    def resolve_unknown_presence(self,intent:OrderIntent,*,broker_order_exists:bool)->LifecycleDecision:
        """Resolve UNKNOWN only from an explicit exact-identity broker query."""
        if not isinstance(intent,OrderIntent): raise ValueError("intent must be OrderIntent")
        if type(broker_order_exists) is not bool: raise ValueError("broker_order_exists must be bool")
        current=self.ledger.get(intent.order_id)
        if current is None or current.state is not SubmissionState.UNKNOWN:
            raise ValueError("intent is not awaiting broker presence reconciliation")
        record=self.ledger.reconcile_unknown(intent.order_id,broker_order_exists=broker_order_exists)
        if record.state is SubmissionState.ACCEPTED:
            return LifecycleDecision(True,record.state,())
        return LifecycleDecision(False,record.state,("broker explicitly confirmed order absence",))
