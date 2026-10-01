import pytest
from execution.execution_journal import build_snapshot,deserialize_snapshot,serialize_snapshot
from execution.idempotency import IdempotencyLedger,SubmissionState
from execution.reconciliation import OrderIntent
from core.enums import Direction

def _i(x): return OrderIntent(x,"XAUUSD",Direction.BUY,0.03,2500.0)

def test_journal_restores_unknown_without_becoming_retryable():
    ledger=IdempotencyLedger(); ledger.begin(_i("A")); ledger.mark_transport_failure("A")
    snap=deserialize_snapshot(serialize_snapshot(build_snapshot(ledger.records())))
    restored=IdempotencyLedger.restore(snap.records)
    assert restored.get("A").state is SubmissionState.UNKNOWN
    with pytest.raises(ValueError,match="cannot be resubmitted"): restored.begin(_i("A"))

def test_journal_restores_inflight_without_duplicate_submission():
    ledger=IdempotencyLedger(); ledger.begin(_i("A"))
    restored=IdempotencyLedger.restore(deserialize_snapshot(serialize_snapshot(build_snapshot(ledger.records()))).records)
    assert restored.get("A").state is SubmissionState.IN_FLIGHT
    with pytest.raises(ValueError,match="cannot be resubmitted"): restored.begin(_i("A"))

def test_restore_rejects_duplicate_records():
    ledger=IdempotencyLedger(); ledger.begin(_i("A")); r=ledger.get("A")
    with pytest.raises(ValueError,match="duplicate"): IdempotencyLedger.restore((r,r))
