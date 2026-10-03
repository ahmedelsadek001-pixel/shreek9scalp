"""Broker outcome evidence must remain bound to the original intent."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.enums import Direction
from execution.broker_outcome import (
    classify_broker_outcome,
    is_broker_outcome_issued,
)
from execution.execution_journal import build_snapshot
from execution.execution_lifecycle import ExecutionLifecycleCoordinator
from execution.idempotency import IdempotencyLedger, SubmissionState
from execution.quote_safety import evaluate_quote_safety
from execution.reconciliation import (
    ExecutionReport,
    OrderIntent,
    reconcile_execution,
)
from execution.recovery import ShadowRecovery
from execution.safety_gate import (
    derive_execution_safety_evidence,
    evaluate_execution_safety,
)
from execution.shadow import ShadowExecution


NOW = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)


def _intent(order_id: str = "bound-outcome") -> OrderIntent:
    return OrderIntent(order_id, "XAUUSD", Direction.BUY, .03, 2500.0)


def _accepted(intent: OrderIntent):
    return classify_broker_outcome(
        intent=intent, acknowledged=True, accepted=True)


def _derive(intent: OrderIntent, outcomes):
    ledger = IdempotencyLedger()
    ledger.begin(intent)
    ledger.finish(intent.order_id, SubmissionState.ACCEPTED)
    quote = evaluate_quote_safety(
        symbol=intent.symbol, direction=intent.direction,
        quote_time=NOW, now=NOW, intended_price=intent.expected_price,
        market_price=intent.expected_price, max_age_seconds=2,
        max_deviation_points=3, point_size=.01,
    )
    reconciliation = reconcile_execution(
        intent,
        ExecutionReport(
            intent.order_id, intent.symbol, intent.direction,
            intent.volume, intent.expected_price,
        ),
    )
    return derive_execution_safety_evidence(
        quote_decisions=(quote,),
        outcome_decisions=outcomes,
        ledger=ledger,
        journal=build_snapshot(ledger.records()),
        recovery=ShadowRecovery(ShadowExecution()).admission(),
        reconciliation_results=(reconciliation,),
        live_execution_enabled=False,
    )


def test_classifier_requires_explicit_intent_binding():
    with pytest.raises(TypeError):
        classify_broker_outcome(acknowledged=True, accepted=True)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("order_id", "other-order"),
        ("symbol", "EURUSD"),
        ("direction", Direction.SELL),
        ("volume", .04),
        ("expected_price", 2500.01),
    ],
)
def test_issued_outcome_cannot_change_a_different_intent(field, replacement):
    original = _intent()
    substituted = replace(original, **{field: replacement})
    ledger = IdempotencyLedger()
    ledger.begin(substituted)

    with pytest.raises(ValueError, match="does not match original intent"):
        ExecutionLifecycleCoordinator(ledger).apply_outcome(
            substituted, _accepted(original))

    assert ledger.get(substituted.order_id).state is SubmissionState.IN_FLIGHT


def test_matching_issued_outcome_can_change_its_original_intent():
    intent = _intent()
    ledger = IdempotencyLedger()
    ledger.begin(intent)

    decision = ExecutionLifecycleCoordinator(ledger).apply_outcome(
        intent, _accepted(intent))

    assert decision.safe is True
    assert decision.state is SubmissionState.ACCEPTED


def test_outcome_for_different_intent_cannot_validate_execution_safety():
    source = _intent("source-outcome")
    target = _intent("target-evidence")

    evidence = _derive(target, (_accepted(source),))

    assert evidence.outcome_classification_validated is False
    assert evaluate_execution_safety(evidence).ready is False


def test_outcome_for_matching_intent_validates_execution_safety():
    intent = _intent("matching-evidence")

    evidence = _derive(intent, (_accepted(intent),))

    assert evidence.outcome_classification_validated is True
    assert evaluate_execution_safety(evidence).ready is True


def test_edited_intent_binding_invalidates_issued_outcome():
    decision = _accepted(_intent())

    object.__setattr__(decision, "intent_fingerprint", "0" * 64)

    assert is_broker_outcome_issued(decision) is False
