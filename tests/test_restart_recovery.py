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
