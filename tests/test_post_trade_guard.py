from core.enums import Direction
from execution.post_trade_guard import evaluate_post_trade
from execution.quality_gate import (
    ExecutionQualityDecision,
    ExecutionQualityPolicy,
    evaluate_quality,
)
from execution.reconciliation import (
    ExecutionReport,
    OrderIntent,
    ReconciliationResult,
    reconcile_execution,
)


POLICY = ExecutionQualityPolicy(0.2, 0.5, 250.0)


def _artifacts(*, spread=0.1, latency_ms=10.0):
    intent = OrderIntent("A", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    report = ExecutionReport("A", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    return (
        reconcile_execution(intent, report),
        evaluate_quality(
            POLICY,
            intent=intent,
            report=report,
            spread=spread,
            latency_ms=latency_ms,
        ),
    )


def test_post_trade_accepts_only_reconciled_quality_fill():
    reconciliation, quality = _artifacts()
    decision = evaluate_post_trade(
        reconciliation=reconciliation,
        quality=quality,
    )
    assert decision.accepted is True
    assert decision.reasons == ()


def test_post_trade_blocks_unreconciled_fill():
    decision = evaluate_post_trade(
        reconciliation=ReconciliationResult(False, ("fill price outside tolerance",)),
        quality=ExecutionQualityDecision(True, ()),
    )
    assert decision.accepted is False
    assert "reconciliation: fill price outside tolerance" in decision.reasons


def test_post_trade_blocks_bad_execution_quality():
    reconciliation, quality = _artifacts(latency_ms=400.0)
    decision = evaluate_post_trade(
        reconciliation=reconciliation,
        quality=quality,
    )
    assert decision.accepted is False
    assert "quality: latency outside limit" in decision.reasons


def test_post_trade_fails_closed_on_malformed_results():
    decision = evaluate_post_trade(reconciliation=None, quality=None)
    assert decision.accepted is False
    assert "reconciliation result malformed" in decision.reasons
    assert "execution quality result malformed" in decision.reasons


def test_post_trade_fails_closed_on_malformed_decision_fields():
    decision = evaluate_post_trade(
        reconciliation=ReconciliationResult(1, ()),
        quality=ExecutionQualityDecision(True, ("ok", 1)),
    )

    assert decision.accepted is False
    assert "reconciliation result malformed" in decision.reasons
    assert "execution quality reasons malformed" in decision.reasons


def test_post_trade_blocks_internally_inconsistent_reconciliation():
    decision = evaluate_post_trade(
        reconciliation=ReconciliationResult(True, ("unexpected reason",)),
        quality=ExecutionQualityDecision(True, ()),
    )

    assert decision.accepted is False
    assert "reconciliation decision internally inconsistent" in decision.reasons


def test_post_trade_blocks_internally_inconsistent_quality():
    reconciliation, _ = _artifacts()
    decision = evaluate_post_trade(
        reconciliation=reconciliation,
        quality=ExecutionQualityDecision(True, ("unexpected reason",)),
    )

    assert decision.accepted is False
    assert "execution quality decision internally inconsistent" in decision.reasons
