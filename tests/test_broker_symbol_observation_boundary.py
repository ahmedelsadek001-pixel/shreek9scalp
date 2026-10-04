"""Broker observations cannot redefine symbol identity at admission."""
from __future__ import annotations

from datetime import datetime, timezone

from core.enums import Direction
from execution.broker_safety import BrokerSafetyPolicy
from execution.execution_gate import evaluate_environment_gate, is_gate_issued
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.idempotency import IdempotencyLedger
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.quote_safety import evaluate_quote_safety
from execution.reconciliation import OrderIntent
from execution.recovery import ShadowRecovery
from execution.shadow import ShadowExecution


class SpoofedSymbol(str):
    """Use caller-controlled equality to impersonate an allowlisted symbol."""

    def __hash__(self) -> int:
        return hash("XAUUSD")

    def __eq__(self, other: object) -> bool:
        return True


class RaisingHashSymbol(str):
    def __hash__(self) -> int:
        raise RuntimeError("caller-controlled symbol hash")


def _gate(symbol: object):
    now = datetime.now(timezone.utc)
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(
            now, now, now, True, True),
        broker_policy=BrokerSafetyPolicy(
            frozenset({"XAUUSD"}), 1.0, 0.01, 1.0, 0.5),
        symbol=symbol,
        spread=0.2,
        volume=0.03,
        slippage=0.1,
        kill_switch_active=False,
        recovery=ShadowRecovery(ShadowExecution()).admission(),
    )


def _attempt(gate, symbol: str):
    now = datetime.now(timezone.utc)
    intent = OrderIntent(
        "BROKER-OBSERVED-SYMBOL", symbol, Direction.BUY, 0.03, 2500.0)
    quote = evaluate_quote_safety(
        symbol=symbol,
        direction=Direction.BUY,
        quote_time=now,
        now=now,
        intended_price=2500.0,
        market_price=2500.0,
        max_age_seconds=2,
        max_deviation_points=3,
        point_size=0.01,
    )
    calls: list[str] = []
    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.symbol) or "offline-accepted",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)
    return result, calls


def test_symbol_equality_spoof_cannot_escape_allowlist_or_reach_transport():
    gate = _gate(SpoofedSymbol("BTCUSD"))

    result, calls = _attempt(gate, "BTCUSD")

    assert not gate.allowed
    assert gate.reasons == (
        "broker: broker symbol must be exact and non-empty",
    )
    assert not result.executed
    assert calls == []


def test_raising_symbol_hash_becomes_an_issued_denial():
    gate = _gate(RaisingHashSymbol("XAUUSD"))

    assert not gate.allowed
    assert gate.reasons == (
        "broker: broker symbol must be exact and non-empty",
    )
    assert is_gate_issued(gate)


def test_exact_allowlisted_symbol_retains_offline_control_path():
    gate = _gate("XAUUSD")

    result, calls = _attempt(gate, "XAUUSD")

    assert gate.allowed
    assert result.executed
    assert calls == ["XAUUSD"]
