from datetime import datetime, timezone

import pytest

from core.enums import Direction
from execution.recovery import RecoveryState, ShadowRecovery
from execution.shadow import ShadowExecution
from execution.shadow_pipeline import PaperShadowBridge
from paper_trading.engine import PaperOrder, PaperTradingEngine


def _order():
    return PaperOrder(
        "XAUUSD",
        Direction.BUY,
        100.0,
        99.0,
        1.0,
        datetime(2026, 9, 12, 10, tzinfo=timezone.utc),
    )


def test_disconnect_is_fail_closed_for_admission():
    recovery = ShadowRecovery(ShadowExecution())
    decision = recovery.disconnect()
    assert decision.state is RecoveryState.DISCONNECTED
    assert not decision.can_submit
    assert not recovery.admission().can_submit


def test_recovery_cannot_complete_with_pending_shadow_order():
    shadow = ShadowExecution()
    bridge = PaperShadowBridge(shadow)
    bridge.register_paper_order(_order())
    recovery = ShadowRecovery(shadow)

    recovery.disconnect()
    recovery.begin_recovery()
    decision = recovery.complete_recovery()

    assert decision.state is RecoveryState.RECOVERING
    assert not decision.can_submit
    assert "reconciliation" in decision.reason


def test_failed_paper_submission_does_not_leave_duplicate_reservation():
    engine = PaperTradingEngine()
    engine.submit(_order())
    shadow = ShadowExecution()
    bridge = PaperShadowBridge(shadow)
    bridge.register_paper_order(_order())

    # The shadow layer is observational only; a second paper submission must fail.
    with pytest.raises(RuntimeError):
        engine.submit(_order())

    assert engine.open_order is not None
    assert len(shadow.submissions) == 1
