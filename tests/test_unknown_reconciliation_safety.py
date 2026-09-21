from core.enums import Direction
from execution.broker_outcome import classify_broker_outcome
from execution.execution_lifecycle import ExecutionLifecycleCoordinator
from execution.idempotency import IdempotencyLedger,SubmissionState
from execution.reconciliation import ExecutionReport,OrderIntent

def setup_unknown():
    i=OrderIntent("U-1","XAUUSD",Direction.BUY,.03,2500)
    l=IdempotencyLedger(); l.begin(i); c=ExecutionLifecycleCoordinator(l)
    c.apply_outcome(i,classify_broker_outcome(acknowledged=False,accepted=None))
    return i,l,c

def test_mismatched_report_does_not_prove_unknown_order_absent():
    i,l,c=setup_unknown()
    r=c.reconcile(i,ExecutionReport("OTHER","XAUUSD",Direction.BUY,.03,2500))
    assert not r.matched
    assert l.get(i.order_id).state is SubmissionState.UNKNOWN

def test_exact_report_resolves_unknown_to_accepted():
    i,l,c=setup_unknown()
    assert c.reconcile(i,ExecutionReport(i.order_id,i.symbol,i.direction,i.volume,i.expected_price)).matched
    assert l.get(i.order_id).state is SubmissionState.ACCEPTED

def test_explicit_broker_absence_resolves_unknown_to_rejected():
    i,l,c=setup_unknown()
    d=c.resolve_unknown_presence(i,broker_order_exists=False)
    assert not d.safe and d.state is SubmissionState.REJECTED

def test_explicit_broker_presence_resolves_unknown_to_accepted():
    i,l,c=setup_unknown()
    d=c.resolve_unknown_presence(i,broker_order_exists=True)
    assert d.safe and d.state is SubmissionState.ACCEPTED
