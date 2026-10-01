import pytest
from core.enums import Direction
from execution.broker_outcome import classify_broker_outcome
from execution.broker_outcome import BrokerOutcome, BrokerOutcomeDecision
from execution.execution_lifecycle import ExecutionLifecycleCoordinator
from execution.idempotency import IdempotencyLedger,SubmissionState
from execution.reconciliation import ExecutionReport,OrderIntent

def intent(): return OrderIntent("O1","XAUUSD",Direction.BUY,0.03,2500.0)

def test_accepted_then_reconciled():
    ledger=IdempotencyLedger(); i=intent(); ledger.begin(i)
    c=ExecutionLifecycleCoordinator(ledger)
    d=c.apply_outcome(i,classify_broker_outcome(acknowledged=True,accepted=True))
    assert d.safe and d.state is SubmissionState.ACCEPTED
    r=c.reconcile(i,ExecutionReport("O1","XAUUSD",Direction.BUY,0.03,2500.0))
    assert r.matched

def test_unknown_blocks_and_requires_reconciliation():
    ledger=IdempotencyLedger(); i=intent(); ledger.begin(i)
    c=ExecutionLifecycleCoordinator(ledger)
    d=c.apply_outcome(i,classify_broker_outcome(acknowledged=False,accepted=None))
    assert not d.safe and d.state is SubmissionState.UNKNOWN
    with pytest.raises(ValueError): ledger.begin(i)
    r=c.reconcile(i,ExecutionReport("O1","XAUUSD",Direction.BUY,0.03,2500.0))
    assert r.matched
    assert ledger.get("O1").state is SubmissionState.ACCEPTED

def test_unknown_mismatch_remains_unknown_and_blocks_retry():
    ledger=IdempotencyLedger(); i=intent(); ledger.begin(i)
    c=ExecutionLifecycleCoordinator(ledger)
    c.apply_outcome(i,classify_broker_outcome(acknowledged=False,accepted=None))
    r=c.reconcile(i,ExecutionReport("WRONG","XAUUSD",Direction.BUY,0.03,2500.0))
    assert not r.matched
    assert ledger.get("O1").state is SubmissionState.UNKNOWN
    with pytest.raises(ValueError, match="unknown"): ledger.begin(i)

def test_explicit_retryable_rejection_still_requires_new_identity():
    ledger=IdempotencyLedger(); i=intent(); ledger.begin(i)
    c=ExecutionLifecycleCoordinator(ledger)
    d=c.apply_outcome(i,classify_broker_outcome(acknowledged=True,accepted=False,rejection_code="REQUOTE"))
    assert d.state is SubmissionState.REJECTED
    with pytest.raises(ValueError,match="new identity"): ledger.begin(i)

@pytest.mark.parametrize(
    "outcome",
    [
        BrokerOutcomeDecision(BrokerOutcome.REJECTED_FINAL, True, "bad retry flag"),
        BrokerOutcomeDecision(BrokerOutcome.ACCEPTED, False, ""),
        BrokerOutcomeDecision(BrokerOutcome.UNKNOWN, False, "   "),
    ],
)
def test_inconsistent_or_empty_broker_outcome_is_rejected_before_state_change(outcome):
    ledger=IdempotencyLedger(); i=intent(); ledger.begin(i)
    c=ExecutionLifecycleCoordinator(ledger)
    with pytest.raises(ValueError):
        c.apply_outcome(i, outcome)
    assert ledger.get("O1").state is SubmissionState.IN_FLIGHT
