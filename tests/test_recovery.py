from core.enums import Direction
from execution.reconciliation import ExecutionReport, OrderIntent
from execution.recovery import RecoveryState, ShadowRecovery
from execution.shadow import ShadowExecution
import pytest


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
