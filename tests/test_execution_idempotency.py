import pytest

from core.enums import Direction
from execution.idempotency import IdempotencyLedger, SubmissionState
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
