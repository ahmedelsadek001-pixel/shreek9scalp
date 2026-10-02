import pytest

from core.enums import Direction
from execution.idempotency import IdempotencyLedger, SubmissionRecord, SubmissionState
from execution.reconciliation import OrderIntent


def _intent(order_id="ORD-001"):
    return OrderIntent(order_id, "XAUUSD", Direction.BUY, 0.03, 2500.0)


def test_duplicate_inflight_and_accepted_submission_fail_closed():
    ledger=IdempotencyLedger(); intent=_intent()
    assert ledger.begin(intent).state is SubmissionState.IN_FLIGHT
    with pytest.raises(ValueError,match="cannot be resubmitted"): ledger.begin(intent)
    ledger.finish(intent.order_id,SubmissionState.ACCEPTED)
    with pytest.raises(ValueError,match="cannot be resubmitted"): ledger.begin(intent)


def test_transport_failure_becomes_unknown_and_blocks_retry():
    ledger=IdempotencyLedger(); intent=_intent()
    ledger.begin(intent); record=ledger.mark_transport_failure(intent.order_id)
    assert record.state is SubmissionState.UNKNOWN
    with pytest.raises(ValueError,match="cannot be resubmitted"): ledger.begin(intent)


def test_unknown_requires_explicit_reconciliation():
    ledger=IdempotencyLedger(); intent=_intent()
    ledger.begin(intent); ledger.mark_transport_failure(intent.order_id)
    assert ledger.reconcile_unknown(intent.order_id,broker_order_exists=True).state is SubmissionState.ACCEPTED


def test_rejected_identity_cannot_be_reused():
    ledger=IdempotencyLedger(); intent=_intent()
    ledger.begin(intent); ledger.finish(intent.order_id,SubmissionState.REJECTED)
    with pytest.raises(ValueError,match="new identity"): ledger.begin(intent)


def test_finish_without_inflight_fails_closed():
    ledger=IdempotencyLedger()
    with pytest.raises(ValueError,match="no in-flight"): ledger.finish("ORD-X",SubmissionState.ACCEPTED)


@pytest.mark.parametrize("state",[SubmissionState.NEW,SubmissionState.IN_FLIGHT,object()])
def test_finish_rejects_non_terminal_state(state):
    ledger=IdempotencyLedger(); ledger.begin(_intent())
    with pytest.raises(ValueError): ledger.finish("ORD-001",state)


def test_reserved_identity_cannot_be_reused_if_state_is_corrupted_to_new():
    ledger = IdempotencyLedger()
    intent = _intent()
    record = ledger.begin(intent)
    object.__setattr__(record, "state", SubmissionState.NEW)
    with pytest.raises(ValueError, match="malformed submission state"):
        ledger.begin(intent)
    with pytest.raises(ValueError, match="malformed submission state"):
        ledger.get(intent.order_id)
    assert ledger._records[intent.order_id] is record
    assert record.attempts == 1


@pytest.mark.parametrize("corruption", ["moved", "padded", "record", "alias"])
@pytest.mark.parametrize("operation", ["records", "get", "begin", "finish", "reconcile"])
def test_ledger_rejects_mismatched_storage_identity_without_mutation(corruption, operation):
    ledger = IdempotencyLedger()
    record = ledger.begin(_intent("A"))
    if operation == "reconcile":
        record = ledger.mark_transport_failure("A")
    if corruption == "moved":
        ledger._records = {"B": record}
    elif corruption == "padded":
        ledger._records = {" A ": record}
    elif corruption == "record":
        ledger._records = {"A": SubmissionRecord("B", record.state, record.attempts)}
    else:
        ledger._records["B"] = record
    before = dict(ledger._records)
    with pytest.raises(ValueError, match="order identity"):
        if operation == "records":
            ledger.records()
        elif operation == "get":
            ledger.get("A")
        elif operation == "begin":
            ledger.begin(_intent("C"))
        elif operation == "finish":
            ledger.finish("A", SubmissionState.ACCEPTED)
        else:
            ledger.reconcile_unknown("A", broker_order_exists=False)
    assert ledger._records == before


def test_normalized_input_identity_remains_usable_and_nonretryable():
    ledger = IdempotencyLedger()
    ledger.begin(_intent(" A "))
    ledger.mark_transport_failure(" A ")
    ledger.reconcile_unknown(" A ", broker_order_exists=True)
    assert ledger.records() == (SubmissionRecord("A", SubmissionState.ACCEPTED, 1),)
    assert ledger.get(" A ") == ledger.get("A")
    with pytest.raises(ValueError, match="cannot be resubmitted"):
        ledger.begin(_intent(" A "))


@pytest.mark.parametrize("invalid_fields", [
    {"state": "unknown"}, {"state": None}, {"state": SubmissionState.NEW},
    {"attempts": 0}, {"attempts": True}, {"attempts": 1.5},
])
@pytest.mark.parametrize("operation", ["records", "get", "begin", "finish", "reconcile"])
def test_malformed_record_blocks_ledger_reads_and_transitions(invalid_fields, operation):
    ledger = IdempotencyLedger()
    record = ledger.begin(_intent("A"))
    if operation == "reconcile":
        record = ledger.mark_transport_failure("A")
    values = dict(order_id=record.order_id, state=record.state, attempts=record.attempts)
    values.update(invalid_fields)
    ledger._records["A"] = SubmissionRecord(**values)
    before = dict(ledger._records)
    with pytest.raises(ValueError, match="malformed"):
        if operation == "records":
            ledger.records()
        elif operation == "get":
            ledger.get("A")
        elif operation == "begin":
            ledger.begin(_intent("B"))
        elif operation == "finish":
            ledger.finish("A", SubmissionState.ACCEPTED)
        else:
            ledger.reconcile_unknown("A", broker_order_exists=False)
    assert ledger._records == before
