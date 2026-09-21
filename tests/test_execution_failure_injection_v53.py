"""Failure-injection coverage for the V5.3 execution safety boundary."""
import pytest
from core.enums import Direction
from execution.broker_outcome import classify_broker_outcome
from execution.execution_lifecycle import ExecutionLifecycleCoordinator
from execution.idempotency import IdempotencyLedger, SubmissionState
from execution.reconciliation import ExecutionReport, OrderIntent

def _intent(): return OrderIntent("FAIL-001","XAUUSD",Direction.BUY,0.03,2500.0)

def _unknown():
    ledger=IdempotencyLedger(); i=_intent(); ledger.begin(i)
    c=ExecutionLifecycleCoordinator(ledger)
    c.apply_outcome(i,classify_broker_outcome(acknowledged=False,accepted=None))
    return ledger,c,i

def test_disconnect_after_send_never_permits_blind_retry():
    ledger,_,i=_unknown()
    assert ledger.get(i.order_id).state is SubmissionState.UNKNOWN
    with pytest.raises(ValueError,match="cannot be resubmitted"): ledger.begin(i)

@pytest.mark.parametrize("report",[
    ExecutionReport("WRONG","XAUUSD",Direction.BUY,0.03,2500.0),
    ExecutionReport("FAIL-001","EURUSD",Direction.BUY,0.03,2500.0),
    ExecutionReport("FAIL-001","XAUUSD",Direction.SELL,0.03,2500.0),
    ExecutionReport("FAIL-001","XAUUSD",Direction.BUY,0.04,2500.0),
    ExecutionReport("FAIL-001","XAUUSD",Direction.BUY,0.03,2502.0),
])
def test_unknown_execution_mismatch_fails_closed(report):
    ledger,c,i=_unknown()
    result=c.reconcile(i,report)
    assert not result.matched
    assert ledger.get(i.order_id).state is SubmissionState.UNKNOWN

def test_repeated_mismatched_reports_leave_unknown_fail_closed():
    ledger,c,i=_unknown()
    bad=ExecutionReport("WRONG","XAUUSD",Direction.BUY,0.03,2500.0)
    assert not c.reconcile(i,bad).matched
    assert not c.reconcile(i,bad).matched
    assert ledger.get(i.order_id).state is SubmissionState.UNKNOWN

def test_accepted_fill_mismatch_is_detected_without_mutating_acceptance():
    ledger=IdempotencyLedger(); i=_intent(); ledger.begin(i)
    c=ExecutionLifecycleCoordinator(ledger)
    c.apply_outcome(i,classify_broker_outcome(acknowledged=True,accepted=True))
    result=c.reconcile(i,ExecutionReport(i.order_id,i.symbol,i.direction,i.volume,2505.0),price_tolerance=1.0)
    assert not result.matched
    assert "fill price outside tolerance" in result.reasons
    assert ledger.get(i.order_id).state is SubmissionState.ACCEPTED
