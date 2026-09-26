import pytest

from core.enums import Direction
from execution.reconciliation import ExecutionReport, OrderIntent
from execution.recovery import RecoveryState, ShadowRecovery
from execution.shadow import ShadowExecution


def test_disconnect_blocks_and_clean_recovery_reenables_submission():
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    assert recovery.admission().can_submit
    assert recovery.disconnect().state is RecoveryState.DISCONNECTED
    assert not recovery.admission().can_submit
    assert recovery.begin_recovery().state is RecoveryState.RECOVERING
    recovered = recovery.complete_recovery()
    assert recovered.state is RecoveryState.CONNECTED
    assert recovered.can_submit


def test_recovery_completes_only_after_pending_orders_reconcile():
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    shadow.submit_intent(OrderIntent("sig-1", "XAUUSD", Direction.BUY, 0.03, 2500.0))
    recovery.disconnect()
    recovery.begin_recovery()
    blocked = recovery.complete_recovery()
    assert not blocked.can_submit
    shadow.observe(ExecutionReport("sig-1", "XAUUSD", Direction.BUY, 0.03, 2500.0))
    recovered = recovery.complete_recovery()
    assert recovered.state is RecoveryState.CONNECTED
    assert recovered.can_submit


def test_connected_admission_fails_closed_when_pending_order_exists():
    shadow = ShadowExecution()
    shadow.submit_intent(OrderIntent("sig-pending", "XAUUSD", Direction.BUY, 0.03, 2500.0))
    recovery = ShadowRecovery(shadow)
    decision = recovery.admission()
    assert decision.state is RecoveryState.CONNECTED
    assert not decision.can_submit
    assert "pending shadow orders" in decision.reason


def test_recovery_cannot_begin_from_connected_state():
    recovery = ShadowRecovery(ShadowExecution())
    decision = recovery.begin_recovery()
    assert not decision.can_submit
    assert decision.state is RecoveryState.CONNECTED


def test_recovery_rejects_invalid_shadow_adapter():
    with pytest.raises(TypeError, match="shadow must be ShadowExecution"):
        ShadowRecovery(object())


def test_admission_fails_closed_when_shadow_state_query_raises(monkeypatch):
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)

    def broken_pending():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(shadow, "pending_order_ids", broken_pending)
    decision = recovery.admission()
    assert not decision.can_submit
    assert decision.state is RecoveryState.CONNECTED
    assert decision.reason == "shadow recovery state unavailable"


def test_complete_recovery_stays_recovering_when_shadow_state_is_malformed(monkeypatch):
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    recovery.disconnect()
    recovery.begin_recovery()

    monkeypatch.setattr(shadow, "pending_order_ids", lambda: ["not", "a", "tuple"])
    decision = recovery.complete_recovery()
    assert not decision.can_submit
    assert decision.state is RecoveryState.RECOVERING
    assert decision.reason == "shadow recovery state unavailable"


def test_complete_recovery_rejects_duplicate_or_blank_pending_identity(monkeypatch):
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    recovery.disconnect()
    recovery.begin_recovery()

    for malformed in (("A", "A"), ("",), ("   ",), (7,)):
        monkeypatch.setattr(shadow, "pending_order_ids", lambda value=malformed: value)
        decision = recovery.complete_recovery()
        assert not decision.can_submit
        assert decision.state is RecoveryState.RECOVERING


def test_recovery_normalizes_pending_identity_order(monkeypatch):
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    recovery.disconnect()
    recovery.begin_recovery()
    monkeypatch.setattr(shadow, "pending_order_ids", lambda: ("B", "A"))
    decision = recovery.complete_recovery()
    assert not decision.can_submit
    assert decision.reason == "pending shadow orders require reconciliation"


def test_recovery_state_and_shadow_cannot_be_replaced_directly():
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    with pytest.raises(AttributeError):
        recovery.state = RecoveryState.RECOVERING
    with pytest.raises(AttributeError):
        recovery.shadow = ShadowExecution()
