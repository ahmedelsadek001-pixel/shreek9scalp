import pytest

from core.enums import Direction
from execution.broker_outcome import classify_broker_outcome
from execution.execution_lifecycle import ExecutionLifecycleCoordinator
from execution.idempotency import IdempotencyLedger,SubmissionState
from execution.reconciliation import ExecutionReport,OrderIntent
from execution.restart_recovery import snapshot_unresolved, validate_restart

def setup_unknown(direction=Direction.BUY):
    i=OrderIntent("U-1","XAUUSD",direction,.03,2500)
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


@pytest.mark.parametrize("direction", [Direction.RANGE, Direction.UNKNOWN])
def test_non_execution_direction_cannot_clear_unknown_or_restart_gate(direction):
    intent, ledger, coordinator = setup_unknown(direction)
    before = ledger.records()
    report = ExecutionReport(intent.order_id, intent.symbol, direction, intent.volume, intent.expected_price)
    result = coordinator.reconcile(intent, report)
    assert not result.matched
    assert "invalid direction" in result.reasons
    assert ledger.records() == before
    assert ledger.get(intent.order_id).state is SubmissionState.UNKNOWN
    snapshot = snapshot_unresolved(ledger)
    assert snapshot.unresolved_order_ids == (intent.order_id,)
    assert not validate_restart(snapshot)[0]
    with pytest.raises(ValueError, match="cannot be resubmitted"):
        ledger.begin(intent)


def test_exact_sell_report_resolves_unknown_and_remains_nonretryable():
    intent, ledger, coordinator = setup_unknown(Direction.SELL)
    report = ExecutionReport(intent.order_id, intent.symbol, Direction.SELL, intent.volume, intent.expected_price)
    assert coordinator.reconcile(intent, report).matched
    assert ledger.get(intent.order_id).state is SubmissionState.ACCEPTED
    assert ledger.get(intent.order_id).attempts == 1
    assert validate_restart(snapshot_unresolved(ledger))[0]
    with pytest.raises(ValueError, match="cannot be resubmitted"):
        ledger.begin(intent)
