from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.enums import Direction
from execution.broker_outcome import classify_broker_outcome
from execution.execution_journal import build_snapshot
from execution.idempotency import IdempotencyLedger, SubmissionState
from execution.post_trade_guard import evaluate_post_trade
from execution.quality_gate import (
    ExecutionQualityDecision,
    ExecutionQualityPolicy,
    evaluate_quality,
)
from execution.quote_safety import evaluate_quote_safety
from execution.reconciliation import (
    ExecutionReport,
    OrderIntent,
    ReconciliationResult,
    reconcile_execution,
)
from execution.recovery import ShadowRecovery
from execution.safety_gate import derive_execution_safety_evidence
from execution.shadow import ShadowExecution


NOW = datetime(2026, 10, 3, 8, 30, tzinfo=timezone.utc)
QUALITY_POLICY = ExecutionQualityPolicy(0.2, 0.5, 250.0)


def _intent(**changes):
    values = dict(
        order_id="TARGET", symbol="XAUUSD", direction=Direction.BUY,
        volume=0.03, expected_price=2500.0,
    )
    values.update(changes)
    return OrderIntent(**values)


def _matching_result(intent):
    return reconcile_execution(
        intent,
        ExecutionReport(
            intent.order_id, intent.symbol, intent.direction,
            intent.volume, intent.expected_price,
        ),
    )


def _evidence(result, *, ledger_intent=None):
    intent = ledger_intent or _intent()
    ledger = IdempotencyLedger()
    ledger.begin(intent)
    ledger.finish(intent.order_id, SubmissionState.ACCEPTED)
    quote = evaluate_quote_safety(
        symbol=intent.symbol,
        direction=intent.direction,
        quote_time=NOW,
        now=NOW,
        intended_price=intent.expected_price,
        market_price=intent.expected_price,
        max_age_seconds=2,
        max_deviation_points=3,
        point_size=0.01,
    )
    return derive_execution_safety_evidence(
        quote_decisions=(quote,),
        outcome_decisions=(classify_broker_outcome(
            intent=intent, acknowledged=True, accepted=True),),
        ledger=ledger,
        journal=build_snapshot(ledger.records()),
        recovery=ShadowRecovery(ShadowExecution()).admission(),
        reconciliation_results=(result,),
        live_execution_enabled=False,
    )


def test_forged_matching_reconciliation_cannot_validate_safety_evidence():
    evidence = _evidence(ReconciliationResult(True, ()))

    assert evidence.reconciliation_validated is False


@pytest.mark.parametrize(
    "changes",
    [
        {"order_id": "OTHER"},
        {"symbol": "XAGUSD"},
        {"direction": Direction.SELL},
        {"volume": 0.04},
        {"expected_price": 2501.0},
    ],
)
def test_issued_reconciliation_for_another_intent_cannot_validate_evidence(changes):
    other = _intent(**changes)

    evidence = _evidence(_matching_result(other))

    assert evidence.reconciliation_validated is False


def test_copied_issued_reconciliation_cannot_validate_evidence():
    copied = replace(_matching_result(_intent()))

    assert _evidence(copied).reconciliation_validated is False


def test_edited_issued_reconciliation_cannot_validate_evidence():
    edited = _matching_result(_intent())
    object.__setattr__(edited, "intent_fingerprint", "0" * 64)

    assert _evidence(edited).reconciliation_validated is False


def test_issued_reconciliation_for_ledger_intent_validates_evidence():
    intent = _intent()

    assert _evidence(_matching_result(intent), ledger_intent=intent).reconciliation_validated is True


def test_forged_reconciliation_cannot_pass_post_trade_gate():
    decision = evaluate_post_trade(
        reconciliation=ReconciliationResult(True, ()),
        quality=ExecutionQualityDecision(True, ()),
    )

    assert decision.accepted is False
    assert "reconciliation result not issued by reconciler" in decision.reasons


def test_issued_reconciliation_can_pass_post_trade_gate():
    intent = _intent()
    report = ExecutionReport(
        intent.order_id, intent.symbol, intent.direction,
        intent.volume, intent.expected_price,
    )
    decision = evaluate_post_trade(
        reconciliation=reconcile_execution(intent, report),
        quality=evaluate_quality(
            QUALITY_POLICY,
            intent=intent,
            report=report,
            spread=0.1,
            latency_ms=10.0,
        ),
    )

    assert decision.accepted is True
    assert decision.reasons == ()
