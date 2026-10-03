"""Broker outcome decisions must originate from the classifier."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.enums import Direction
from execution.broker_outcome import (
    BrokerOutcome,
    BrokerOutcomeDecision,
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


NOW = datetime(2026, 10, 3, 7, 0, tzinfo=timezone.utc)


def _intent(order_id: str = "outcome-provenance") -> OrderIntent:
    return OrderIntent(order_id, "XAUUSD", Direction.BUY, .03, 2500.0)


def _apply(outcome: BrokerOutcomeDecision) -> SubmissionState:
    intent = _intent()
    ledger = IdempotencyLedger()
    ledger.begin(intent)
    coordinator = ExecutionLifecycleCoordinator(ledger)
    with pytest.raises(ValueError, match="not issued by classifier"):
        coordinator.apply_outcome(intent, outcome)
    return ledger.get(intent.order_id).state


def _derive(outcomes: tuple[BrokerOutcomeDecision, ...]):
    intent = _intent("outcome-evidence")
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


@pytest.mark.parametrize(
    "forged",
    [
        BrokerOutcomeDecision(BrokerOutcome.ACCEPTED, False, "accepted"),
        BrokerOutcomeDecision(BrokerOutcome.REJECTED_FINAL, False, "rejected"),
        BrokerOutcomeDecision(BrokerOutcome.UNKNOWN, False, "unknown"),
    ],
)
def test_forged_outcome_cannot_change_in_flight_state(forged):
    assert not is_broker_outcome_issued(forged)
    assert _apply(forged) is SubmissionState.IN_FLIGHT


def test_copied_issued_outcome_cannot_change_in_flight_state():
    issued = classify_broker_outcome(acknowledged=True, accepted=True)
    copied = replace(issued)

    assert is_broker_outcome_issued(issued)
    assert not is_broker_outcome_issued(copied)
    assert _apply(copied) is SubmissionState.IN_FLIGHT


def test_edited_issued_outcome_cannot_change_in_flight_state():
    issued = classify_broker_outcome(acknowledged=True, accepted=True)
    object.__setattr__(issued, "reason", "caller-edited")

    assert not is_broker_outcome_issued(issued)
    assert _apply(issued) is SubmissionState.IN_FLIGHT


def test_classifier_issued_outcome_can_change_in_flight_state():
    intent = _intent()
    ledger = IdempotencyLedger()
    ledger.begin(intent)
    outcome = classify_broker_outcome(acknowledged=True, accepted=True)

    decision = ExecutionLifecycleCoordinator(ledger).apply_outcome(
        intent, outcome,
    )

    assert is_broker_outcome_issued(outcome)
    assert decision.safe is True
    assert decision.state is SubmissionState.ACCEPTED


def test_forged_outcome_cannot_validate_execution_safety():
    forged = BrokerOutcomeDecision(BrokerOutcome.ACCEPTED, False, "accepted")

    evidence = _derive((forged,))

    assert evidence.outcome_classification_validated is False
    assert evaluate_execution_safety(evidence).ready is False


def test_copied_issued_outcome_cannot_validate_execution_safety():
    issued = classify_broker_outcome(acknowledged=True, accepted=True)

    evidence = _derive((replace(issued),))

    assert evidence.outcome_classification_validated is False
    assert evaluate_execution_safety(evidence).ready is False


def test_classifier_issued_outcomes_validate_the_control():
    outcomes = (
        classify_broker_outcome(acknowledged=True, accepted=True),
        classify_broker_outcome(acknowledged=False, accepted=None),
        classify_broker_outcome(
            acknowledged=True, accepted=False, rejection_code="REQUOTE"),
    )

    evidence = _derive(outcomes)

    assert evidence.outcome_classification_validated is True
    assert evaluate_execution_safety(evidence).ready is True
