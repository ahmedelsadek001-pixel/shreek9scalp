from datetime import datetime, timezone

from core.enums import Direction
from execution.execution_gate import evaluate_execution_gate
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.recovery import RecoveryState, ShadowRecovery
from execution.shadow import ShadowExecution
from execution.shadow_pipeline import PaperShadowBridge
from paper_trading.engine import PaperFill, PaperOrder


def _order() -> PaperOrder:
    return PaperOrder(
        "XAUUSD", Direction.BUY, 2500.0, 2495.0, 0.03,
        datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc),
    )


def _ready_gate(recovery: ShadowRecovery):
    decision = recovery.admission()
    return evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=decision,
        kill_switch_active=False,
    )


def test_shadow_reconciliation_recovery_reaches_transport_only_after_all_guards() -> None:
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    bridge = PaperShadowBridge(shadow)
    order = _order()
    intent = bridge.register_paper_order("e2e-001", order)

    blocked = recovery.admission()
    assert blocked.state is RecoveryState.CONNECTED
    assert blocked.can_submit is False
    assert blocked.reason == "pending shadow orders require reconciliation"

    blocked_gate = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=blocked,
        kill_switch_active=False,
    )
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda received: calls.append(received.order_id) or "sent")
    blocked_result = adapter.execute_intent(blocked_gate, intent)
    assert blocked_result.executed is False
    assert calls == []

    fill = PaperFill(
        order, 2501.0, 0.03,
        datetime(2026, 9, 13, 10, 1, tzinfo=timezone.utc), "TP",
    )
    reconciliation = bridge.reconcile_paper_fill("e2e-001", fill)
    assert reconciliation.reconciled

    assert recovery.disconnect().state is RecoveryState.DISCONNECTED
    assert recovery.begin_recovery().state is RecoveryState.RECOVERING
    recovered = recovery.complete_recovery()
    assert recovered.state is RecoveryState.CONNECTED
    assert recovered.can_submit is True

    gate = _ready_gate(recovery)
    result = adapter.execute_intent(gate, intent)
    assert result.executed is True
    assert result.result == "sent"
    assert calls == ["e2e-001"]


def test_recovery_never_grants_transport_authority_by_itself() -> None:
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("sent"))

    recovered = recovery.admission()
    assert recovered.can_submit is True
    assert calls == []

    rejected_gate = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=recovered,
        kill_switch_active=True,
    )
    result = adapter.execute(rejected_gate)
    assert result.executed is False
    assert calls == []
