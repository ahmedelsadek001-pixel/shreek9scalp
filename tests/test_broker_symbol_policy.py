"""Broker symbol allowlists must have immutable, exact schema."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.enums import Direction
from execution.broker_safety import BrokerSafetyPolicy
from execution.execution_gate import evaluate_environment_gate
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.idempotency import IdempotencyLedger
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.quote_safety import evaluate_quote_safety
from execution.reconciliation import OrderIntent
from execution.recovery import ShadowRecovery
from execution.shadow import ShadowExecution


def _gate(allowed_symbols: object, symbol: str):
    now = datetime.now(timezone.utc)
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(
            now, now, now, True, True),
        broker_policy=BrokerSafetyPolicy(
            allowed_symbols, 1.0, 0.01, 1.0, 0.5),
        symbol=symbol, spread=0.2, volume=0.03, slippage=0.1,
        kill_switch_active=False,
        recovery=ShadowRecovery(ShadowExecution()).admission(),
    )


def _attempt(gate, symbol: str):
    now = datetime.now(timezone.utc)
    intent = OrderIntent(
        "BROKER-SYMBOL-SCHEMA", symbol, Direction.BUY, 0.03, 2500.0)
    quote = evaluate_quote_safety(
        symbol=symbol, direction=Direction.BUY,
        quote_time=now, now=now,
        intended_price=2500.0, market_price=2500.0,
        max_age_seconds=2, max_deviation_points=3, point_size=0.01,
    )
    calls: list[str] = []
    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.order_id) or "offline-accepted",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)
    return result, calls


def test_string_allowlist_cannot_authorize_substring_transport():
    gate = _gate("XAUUSD", "XAU")

    result, calls = _attempt(gate, "XAU")

    assert not gate.allowed
    assert gate.reasons == (
        "safety evaluation error: allowed_symbols must be an exact frozenset",
    )
    assert not result.executed
    assert calls == []


@pytest.mark.parametrize("symbols", [
    ["XAUUSD"], {"XAUUSD"}, ("XAUUSD",),
])
def test_mutable_or_wrong_allowlist_containers_fail_closed(symbols):
    gate = _gate(symbols, "XAUUSD")

    assert not gate.allowed
    assert gate.reasons == (
        "safety evaluation error: allowed_symbols must be an exact frozenset",
    )


@pytest.mark.parametrize("symbols", [
    frozenset({1}), frozenset({" XAUUSD"}), frozenset({"XAUUSD "}),
])
def test_malformed_allowlist_elements_fail_closed_without_crashing(symbols):
    gate = _gate(symbols, "XAUUSD")

    assert not gate.allowed
    assert gate.reasons == (
        "safety evaluation error: allowed_symbols must be an exact frozenset",
    )


def test_exact_frozen_allowlist_retains_offline_control_path():
    gate = _gate(frozenset({"XAUUSD"}), "XAUUSD")

    result, calls = _attempt(gate, "XAUUSD")

    assert gate.allowed
    assert result.executed
    assert calls == ["BROKER-SYMBOL-SCHEMA"]
