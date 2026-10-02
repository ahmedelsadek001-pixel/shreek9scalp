"""Shadow recovery must retain its own immutable view of an order intent."""
from dataclasses import replace

import pytest

from core.enums import Direction
from execution.reconciliation import ExecutionReport, OrderIntent
from execution.recovery import RecoveryState, ShadowRecovery
from execution.shadow import ShadowExecution


def _intent() -> OrderIntent:
    return OrderIntent("shadow-original", "XAUUSD", Direction.BUY, .03, 2500)


def _alias(shadow: ShadowExecution, original: OrderIntent, source: str) -> OrderIntent:
    if source == "original":
        return original
    if source == "return":
        return shadow.submit_intent(original).intent
    shadow.submit_intent(original)
    return shadow.submissions()[0].intent


@pytest.mark.parametrize("source", ["original", "return", "listing"])
@pytest.mark.parametrize("changes", [
    {"symbol": "EURUSD"}, {"direction": Direction.SELL},
    {"volume": .04}, {"expected_price": 2505},
])
def test_mutating_public_intent_alias_cannot_clear_pending_recovery(source, changes):
    original = _intent()
    shadow = ShadowExecution()
    exposed = _alias(shadow, original, source)
    if source == "original":
        shadow.submit_intent(original)
    recovery = ShadowRecovery(shadow)
    recovery.disconnect()
    recovery.begin_recovery()
    object.__setattr__(exposed, next(iter(changes)), next(iter(changes.values())))

    replacement = replace(original, **changes) if source != "original" else original
    report = ExecutionReport(
        replacement.order_id, replacement.symbol, replacement.direction,
        replacement.volume, replacement.expected_price,
    )
    result = shadow.observe(report)

    assert not result.matched
    assert shadow.pending_order_ids() == ("shadow-original",)
    decision = recovery.complete_recovery()
    assert not decision.can_submit
    assert decision.state is RecoveryState.RECOVERING


@pytest.mark.parametrize("source", ["original", "return", "listing"])
def test_mutating_public_alias_does_not_change_stored_submission(source):
    original = _intent()
    shadow = ShadowExecution()
    exposed = _alias(shadow, original, source)
    if source == "original":
        shadow.submit_intent(original)
    object.__setattr__(exposed, "symbol", "EURUSD")

    stored = shadow.submissions()[0]
    assert stored.intent == _intent()
    assert stored.intent is not original
    assert stored.intent is not exposed

    result = shadow.observe(ExecutionReport(
        "shadow-original", "XAUUSD", Direction.BUY, .03, 2500))
    assert result.matched
    assert shadow.pending_order_ids() == ()


def test_each_submission_listing_is_an_independent_snapshot():
    shadow = ShadowExecution()
    returned = shadow.submit_intent(_intent())
    first = shadow.submissions()[0]
    second = shadow.submissions()[0]

    assert returned is not first and first is not second
    assert returned.intent is not first.intent and first.intent is not second.intent
    assert returned == first == second


def test_matched_report_is_retained_as_an_independent_snapshot():
    shadow = ShadowExecution()
    shadow.submit_intent(_intent())
    report = ExecutionReport(
        "shadow-original", "XAUUSD", Direction.BUY, .03, 2500)

    assert shadow.observe(report).matched
    object.__setattr__(report, "symbol", "EURUSD")

    retained = shadow._reports["shadow-original"]
    assert retained.symbol == "XAUUSD"
    assert retained is not report
    assert shadow.pending_order_ids() == ()
