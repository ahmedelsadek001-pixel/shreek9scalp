from execution.post_trade_guard import evaluate_post_trade
from execution.quality_gate import ExecutionQualityDecision
from execution.reconciliation import ReconciliationResult


def test_post_trade_accepts_only_reconciled_quality_fill():
    decision = evaluate_post_trade(
        reconciliation=ReconciliationResult(True, ()),
        quality=ExecutionQualityDecision(True, ()),
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
    decision = evaluate_post_trade(
        reconciliation=ReconciliationResult(True, ()),
        quality=ExecutionQualityDecision(False, ("latency outside limit",)),
    )
    assert decision.accepted is False
    assert "quality: latency outside limit" in decision.reasons


def test_post_trade_fails_closed_on_malformed_results():
    decision = evaluate_post_trade(reconciliation=None, quality=None)
    assert decision.accepted is False
    assert "reconciliation result malformed" in decision.reasons
    assert "execution quality result malformed" in decision.reasons


def test_post_trade_fails_closed_on_malformed_decision_fields():
    reconciliation = ReconciliationResult(True, ())
    reconciliation.matched = 1  # type: ignore[misc]
    quality = ExecutionQualityDecision(True, ())
    quality.reasons = ("ok", 1)  # type: ignore[misc]

    decision = evaluate_post_trade(reconciliation=reconciliation, quality=quality)

    assert decision.accepted is False
    assert "reconciliation result malformed" in decision.reasons
    assert "execution quality reasons malformed" in decision.reasons
