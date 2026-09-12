from datetime import datetime, timedelta, timezone

from execution.broker_safety import BrokerSafetyPolicy
from execution.execution_gate import evaluate_environment_gate, evaluate_execution_gate
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.recovery import RecoveryDecision, RecoveryState, ShadowRecovery
from execution.reconciliation import ExecutionReport, OrderIntent
from execution.shadow import ShadowExecution


def _ready_recovery() -> RecoveryDecision:
    return RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available")


def test_execution_gate_allows_only_when_every_layer_is_ready():
    decision = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=_ready_recovery(),
        kill_switch_active=False,
    )
    assert decision.allowed is True
    assert decision.reasons == ()


def test_kill_switch_always_blocks():
    decision = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=_ready_recovery(),
        kill_switch_active=True,
    )
    assert decision.allowed is False
    assert "kill switch active" in decision.reasons


def test_recovery_not_ready_blocks_even_if_other_layers_pass():
    decision = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=RecoveryDecision(RecoveryState.RECOVERING, False, "recovery in progress"),
        kill_switch_active=False,
    )
    assert decision.allowed is False
    assert any(item.startswith("recovery:") for item in decision.reasons)


def test_malformed_layer_fails_closed():
    decision = evaluate_execution_gate(
        operational=(True, ()),
        broker=("yes", ()),
        recovery=_ready_recovery(),
        kill_switch_active=False,
    )
    assert decision.allowed is False
    assert "broker decision malformed" in decision.reasons


def test_malformed_recovery_admission_fails_closed():
    decision = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, 1, "execution channel available"),
        kill_switch_active=False,
    )
    assert decision.allowed is False
    assert "recovery decision malformed" in decision.reasons


def test_pending_shadow_order_blocks_unified_gate_admission():
    shadow = ShadowExecution()
    shadow.submit_intent(OrderIntent("ORD-1", "XAUUSD", "BUY", 0.03, 2500.0))
    recovery = ShadowRecovery(shadow)

    recovery_decision = recovery.admission()
    decision = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=recovery_decision,
        kill_switch_active=False,
    )

    assert recovery_decision.can_submit is False
    assert decision.allowed is False
    assert "recovery: execution channel is not ready" in decision.reasons


def test_recovery_failure_injection_keeps_gate_blocked_after_mismatched_fill():
    shadow = ShadowExecution()
    intent = OrderIntent("ORD-2", "XAUUSD", "BUY", 0.03, 2500.0)
    shadow.submit_intent(intent)
    recovery = ShadowRecovery(shadow)

    assert recovery.disconnect().can_submit is False
    assert recovery.begin_recovery().can_submit is False

    result = shadow.observe(ExecutionReport("ORD-2", "XAUUSD", "BUY", 0.02, 2500.0))
    assert result.matched is False
    assert shadow.pending_order_ids() == ("ORD-2",)

    recovery_decision = recovery.complete_recovery()
    gate_decision = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=recovery_decision,
        kill_switch_active=False,
    )

    assert recovery_decision.can_submit is False
    assert recovery_decision.state is RecoveryState.RECOVERING
    assert gate_decision.allowed is False
    assert "recovery: execution channel is not ready" in gate_decision.reasons


def test_environment_gate_rejects_stale_quote():
    observed = datetime.now(timezone.utc)
    snapshot = OperationalSnapshot(
        observed_at=observed,
        quote_time=observed - timedelta(seconds=6),
        heartbeat_at=observed,
        connected=True,
        trading_enabled=True,
    )
    policy = BrokerSafetyPolicy(
        allowed_symbols=frozenset({"XAUUSD"}),
        max_spread=1.0,
        min_volume=0.01,
        max_volume=1.0,
        max_slippage=0.5,
    )
    decision = evaluate_environment_gate(
        operational_policy=OperationalPolicy(max_quote_age_seconds=5.0),
        operational_snapshot=snapshot,
        broker_policy=policy,
        symbol="XAUUSD",
        spread=0.2,
        volume=0.03,
        slippage=0.1,
        kill_switch_active=False,
        recovery=_ready_recovery(),
    )
    assert decision.allowed is False
    assert "operational: quote is stale" in decision.reasons


def test_environment_gate_rejects_disallowed_symbol():
    observed = datetime.now(timezone.utc)
    snapshot = OperationalSnapshot(observed, observed, observed, True, True)
    policy = BrokerSafetyPolicy(
        allowed_symbols=frozenset({"XAUUSD"}),
        max_spread=1.0,
        min_volume=0.01,
        max_volume=1.0,
        max_slippage=0.5,
    )
    decision = evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=snapshot,
        broker_policy=policy,
        symbol="BTCUSD",
        spread=0.2,
        volume=0.03,
        slippage=0.1,
        kill_switch_active=False,
        recovery=_ready_recovery(),
    )
    assert decision.allowed is False
    assert "broker: symbol not allowed" in decision.reasons
