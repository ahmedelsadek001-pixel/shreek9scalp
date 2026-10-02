import pytest
from execution.execution_journal import build_snapshot,deserialize_snapshot,serialize_snapshot
from execution.idempotency import IdempotencyLedger,SubmissionRecord,SubmissionState
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


@pytest.mark.parametrize("attempts", [1, 2])
def test_restore_rejects_new_state_with_prior_attempts(attempts):
    record = SubmissionRecord("A", SubmissionState.NEW, attempts)
    with pytest.raises(ValueError, match="submission state"):
        IdempotencyLedger.restore((record,))


@pytest.mark.parametrize("state", [SubmissionState.ACCEPTED, SubmissionState.REJECTED])
def test_terminal_records_remain_restorable_and_nonretryable(state):
    ledger = IdempotencyLedger()
    ledger.begin(_i("A"))
    ledger.finish("A", state)
    raw = serialize_snapshot(build_snapshot(ledger.records()))
    restored = IdempotencyLedger.restore(deserialize_snapshot(raw).records)
    before = restored.records()
    assert restored.get("A").state is state
    assert restored.get("A").attempts == 1
    with pytest.raises(ValueError):
        restored.begin(_i("A"))
    assert restored.records() == before
    assert serialize_snapshot(build_snapshot(restored.records())) == raw
