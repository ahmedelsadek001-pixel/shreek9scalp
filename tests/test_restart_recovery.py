from core.enums import Direction
from execution.idempotency import IdempotencyLedger
from execution.reconciliation import OrderIntent
from execution.restart_recovery import RecoverySnapshot,snapshot_unresolved,validate_restart

def _i(x): return OrderIntent(x,"XAUUSD",Direction.BUY,0.03,2500.0)

def test_restart_blocks_on_inflight_order():
    l=IdempotencyLedger(); l.begin(_i("A"))
    s=snapshot_unresolved(l); ok,reasons=validate_restart(s)
    assert not ok and "A" in reasons[0]

def test_restart_blocks_on_unknown_order():
    l=IdempotencyLedger(); l.begin(_i("A")); l.mark_transport_failure("A")
    ok,_=validate_restart(snapshot_unresolved(l)); assert not ok

def test_restart_allows_when_no_unresolved_orders():
    ok,reasons=validate_restart(RecoverySnapshot(()))
    assert ok and reasons==()

def test_malformed_or_duplicate_snapshot_fails_closed():
    assert not validate_restart(RecoverySnapshot(("A","A")))[0]
    assert not validate_restart(RecoverySnapshot(("",)))[0]


def test_restart_snapshot_rejects_noncanonical_ordering():
    ok, reasons = validate_restart(RecoverySnapshot(("B", "A")))
    assert not ok
    assert reasons == ("recovery snapshot is not canonical",)


def test_snapshot_unresolved_rejects_corrupt_ledger_identity():
    ledger = IdempotencyLedger()
    ledger.begin(_i("A"))
    record = ledger._records.pop("A")
    ledger._records[""] = record
    try:
        snapshot_unresolved(ledger)
    except ValueError as exc:
        assert "malformed order identity" in str(exc)
    else:
        raise AssertionError("corrupt ledger identity must fail closed")


def test_snapshot_unresolved_rejects_corrupt_submission_state():
    ledger = IdempotencyLedger()
    ledger.begin(_i("A"))
    record = ledger._records["A"]
    object.__setattr__(record, "state", "UNKNOWN")
    try:
        snapshot_unresolved(ledger)
    except ValueError as exc:
        assert "malformed submission state" in str(exc)
    else:
        raise AssertionError("corrupt submission state must fail closed")
