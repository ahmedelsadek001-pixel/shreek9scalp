"""Single fail-closed execution admission gate for SHREEK V5.3.

This module is deliberately broker-agnostic: it combines safety decisions but
never connects to MT5, sends orders, or changes positions. A caller must pass
explicitly validated results from each safety layer before an execution intent
can be admitted.
"""
from __future__ import annotations

from dataclasses import dataclass

from execution.broker_safety import BrokerSafetyPolicy, authorize_environment
from execution.operational_guard import OperationalPolicy, OperationalSnapshot, evaluate_operational_readiness
from execution.recovery import RecoveryDecision, RecoveryState


@dataclass(frozen=True)
class ExecutionGateDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_execution_gate(
    *,
    operational: tuple[bool, tuple[str, ...]],
    broker: tuple[bool, tuple[str, ...]],
    recovery: RecoveryDecision,
    kill_switch_active: bool,
) -> ExecutionGateDecision:
    """Combine independent safety decisions with a mandatory kill switch.

    Any malformed decision or non-boolean kill-switch value fails closed.
    This function grants only *admission* to a downstream adapter; it has no
    broker authority and cannot itself place an order.
    """
    reasons: list[str] = []
    for name, decision in (("operational", operational), ("broker", broker)):
        if not isinstance(decision, tuple) or len(decision) != 2:
            reasons.append(f"{name} decision malformed")
            continue
        allowed, decision_reasons = decision
        if type(allowed) is not bool:
            reasons.append(f"{name} decision malformed")
            continue
        if not isinstance(decision_reasons, tuple) or any(not isinstance(item, str) for item in decision_reasons):
            reasons.append(f"{name} decision reasons malformed")
            continue
        if not allowed:
            reasons.extend(f"{name}: {item}" for item in decision_reasons)
            if not decision_reasons:
                reasons.append(f"{name}: rejected without reason")
    if not isinstance(recovery, RecoveryDecision):
        reasons.append("recovery decision malformed")
    elif not recovery.can_submit or recovery.state is not RecoveryState.CONNECTED:
        reasons.append("recovery: execution channel is not ready")
    if type(kill_switch_active) is not bool:
        reasons.append("kill switch state malformed")
    elif kill_switch_active:
        reasons.append("kill switch active")
    return ExecutionGateDecision(not reasons, tuple(reasons))


def evaluate_environment_gate(
    *,
    operational_policy: OperationalPolicy,
    operational_snapshot: OperationalSnapshot,
    broker_policy: BrokerSafetyPolicy,
    symbol: str,
    spread: float,
    volume: float,
    slippage: float,
    kill_switch_active: bool,
    recovery: RecoveryDecision,
) -> ExecutionGateDecision:
    """Evaluate operational and broker constraints in one fail-closed call."""
    try:
        operational = evaluate_operational_readiness(operational_policy, operational_snapshot)
        broker = authorize_environment(
            broker_policy,
            symbol=symbol,
            spread=spread,
            volume=volume,
            slippage=slippage,
            connected=operational_snapshot.connected,
            trading_enabled=operational_snapshot.trading_enabled,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        return ExecutionGateDecision(False, (f"safety evaluation error: {exc}",))
    return evaluate_execution_gate(
        operational=operational,
        broker=broker,
        recovery=recovery,
        kill_switch_active=kill_switch_active,
    )
