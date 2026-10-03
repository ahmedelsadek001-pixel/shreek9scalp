"""V5.3 quote evidence must originate from the quote-safety gate."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.enums import Direction
from execution.broker_outcome import classify_broker_outcome
from execution.execution_journal import build_snapshot
from execution.idempotency import IdempotencyLedger, SubmissionState
from execution.quote_safety import (
    QuoteSafetyDecision,
    evaluate_quote_safety,
    is_quote_issued,
)
from execution.reconciliation import ExecutionReport, OrderIntent, reconcile_execution
from execution.recovery import ShadowRecovery
from execution.safety_gate import (
    derive_execution_safety_evidence,
    evaluate_execution_safety,
)
from execution.shadow import ShadowExecution


NOW = datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)


def _quote(*, stale: bool = False) -> QuoteSafetyDecision:
    return evaluate_quote_safety(
        symbol="XAUUSD", direction=Direction.BUY,
        quote_time=NOW - timedelta(seconds=3) if stale else NOW,
        now=NOW, intended_price=2500.0, market_price=2500.0,
        max_age_seconds=2, max_deviation_points=3, point_size=.01,
    )


def _derive(quote_decisions: tuple[QuoteSafetyDecision, ...]):
    intent = OrderIntent(
        "quote-evidence", "XAUUSD", Direction.BUY, .03, 2500.0)
    ledger = IdempotencyLedger()
    ledger.begin(intent)
    ledger.finish(intent.order_id, SubmissionState.ACCEPTED)
    reconciliation = reconcile_execution(
        intent,
        ExecutionReport(
            intent.order_id, intent.symbol, intent.direction,
            intent.volume, intent.expected_price,
        ),
    )
    return derive_execution_safety_evidence(
        quote_decisions=quote_decisions,
        outcome_decisions=(classify_broker_outcome(
            acknowledged=True, accepted=True),),
        ledger=ledger,
        journal=build_snapshot(ledger.records()),
        recovery=ShadowRecovery(ShadowExecution()).admission(),
        reconciliation_results=(reconciliation,),
        live_execution_enabled=False,
    )


def test_forged_positive_quote_cannot_validate_execution_safety():
    forged = QuoteSafetyDecision(True, "accepted")

    evidence = _derive((forged,))

    assert not is_quote_issued(forged)
    assert evidence.quote_safety_validated is False
    assert evaluate_execution_safety(evidence).ready is False


def test_issued_positive_quote_validates_execution_safety():
    quote = _quote()

    evidence = _derive((quote,))

    assert is_quote_issued(quote)
    assert evidence.quote_safety_validated is True
    assert evaluate_execution_safety(evidence).ready is True


def test_issued_rejection_is_valid_evidence_that_quote_gate_ran():
    rejected = _quote(stale=True)

    evidence = _derive((rejected,))

    assert not rejected.allowed
    assert is_quote_issued(rejected)
    assert evidence.quote_safety_validated is True
    assert evaluate_execution_safety(evidence).ready is True


def test_mixed_issued_quote_outcomes_validate_the_control():
    accepted = _quote()
    rejected = _quote(stale=True)

    evidence = _derive((accepted, rejected))

    assert is_quote_issued(accepted)
    assert is_quote_issued(rejected)
    assert evidence.quote_safety_validated is True


def test_copied_issued_quote_cannot_validate_execution_safety():
    copied = replace(_quote())

    evidence = _derive((copied,))

    assert not is_quote_issued(copied)
    assert evidence.quote_safety_validated is False


def test_edited_issued_quote_cannot_validate_execution_safety():
    quote = _quote()
    object.__setattr__(quote, "reason", "caller-edited")

    evidence = _derive((quote,))

    assert not is_quote_issued(quote)
    assert evidence.quote_safety_validated is False
