from core.enums import Direction
from execution.reconciliation import ExecutionReport, OrderIntent
from execution.shadow import ShadowExecution


def _intent() -> OrderIntent:
    return OrderIntent("sig-001", "XAUUSD", Direction.BUY, 0.03, 2500.0)


def test_shadow_requires_reconciliation_before_completion():
    shadow = ShadowExecution()
    shadow.submit_intent(_intent())
    assert shadow.pending_order_ids() == ("sig-001",)
    result = shadow.observe(ExecutionReport("sig-001", "XAUUSD", Direction.BUY, 0.03, 2500.0))
    assert result.matched
    assert shadow.pending_order_ids() == ()


def test_shadow_rejects_unknown_report():
    shadow = ShadowExecution()
    result = shadow.observe(ExecutionReport("unknown", "XAUUSD", Direction.BUY, 0.03, 2500.0))
    assert not result.matched
    assert result.reasons == ("unknown order identity",)


def test_shadow_rejects_duplicate_submission_and_report():
    shadow = ShadowExecution()
    intent = _intent()
    shadow.submit_intent(intent)
    try:
        shadow.submit_intent(intent)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate intent must fail")

    report = ExecutionReport("sig-001", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    assert shadow.observe(report).matched
    duplicate = shadow.observe(report)
    assert not duplicate.matched
    assert duplicate.reasons == ("duplicate execution report",)


def test_shadow_keeps_mismatched_report_pending():
    shadow = ShadowExecution()
    shadow.submit_intent(_intent())
    result = shadow.observe(ExecutionReport("sig-001", "XAUUSD", Direction.SELL, 0.03, 2500.0))
    assert not result.matched
    assert shadow.pending_order_ids() == ("sig-001",)
