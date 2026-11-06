"""Environment admission must be current when transport consumes it."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.enums import Direction
from execution import execution_gate, guarded_adapter
from execution.broker_safety import BrokerSafetyPolicy
from execution.execution_gate import evaluate_environment_gate
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.idempotency import IdempotencyLedger
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.quote_safety import evaluate_quote_safety
from execution.reconciliation import OrderIntent
from execution.recovery import ShadowRecovery
from execution.shadow import ShadowExecution


def _gate(
    observed_at: datetime,
    policy: OperationalPolicy | None = None,
):
    return evaluate_environment_gate(
        operational_policy=policy or OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(
            observed_at, observed_at, observed_at, True, True),
        broker_policy=BrokerSafetyPolicy(
            frozenset({"XAUUSD"}), 1.0, .01, 1.0, .5),
        symbol="XAUUSD", spread=.2, volume=.03, slippage=.1,
        kill_switch_active=False,
        recovery=ShadowRecovery(ShadowExecution()).admission(),
    )


def _attempt(gate, now: datetime, order_id: str, monkeypatch):
    intent = OrderIntent(order_id, "XAUUSD", Direction.BUY, .03, 2500)
    quote = evaluate_quote_safety(
        symbol=intent.symbol, direction=intent.direction,
        quote_time=now, now=now, intended_price=intent.expected_price,
        market_price=intent.expected_price, max_age_seconds=2,
        max_deviation_points=3, point_size=.01,
    )
    calls: list[str] = []
    monkeypatch.setattr(guarded_adapter, "utc_now", lambda: now)
    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.order_id) or "offline-accepted",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)
    return result, calls


def test_old_environment_observation_cannot_authorize_transport(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)
    gate = _gate(current - timedelta(days=30))

    result, calls = _attempt(gate, current, "old-observation", monkeypatch)

    assert not gate.allowed
    assert "operational: environment observation is stale" in gate.reasons
    assert not result.executed
    assert calls == []


def test_environment_gate_expires_before_later_fresh_quote(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)
    gate = _gate(current)

    result, calls = _attempt(
        gate, current + timedelta(seconds=10), "expired-gate", monkeypatch)

    assert gate.allowed
    assert not result.executed
    assert result.reasons == (
        "execution gate decision not issued by execution gate",)
    assert calls == []


def test_current_environment_gate_reaches_offline_control(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)
    gate = _gate(current)

    result, calls = _attempt(
        gate, current + timedelta(seconds=1), "current-gate", monkeypatch)

    assert gate.allowed
    assert result.executed
    assert calls == ["current-gate"]


def test_environment_gate_age_limit_is_inclusive(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)
    gate = _gate(current)

    result, calls = _attempt(
        gate, current + timedelta(seconds=5), "boundary-gate", monkeypatch)

    assert result.executed
    assert calls == ["boundary-gate"]


def test_environment_gate_rejects_clock_rollback(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)
    gate = _gate(current)

    result, calls = _attempt(
        gate, current - timedelta(seconds=1), "rollback-gate", monkeypatch)

    assert not result.executed
    assert result.reasons == (
        "execution gate decision not issued by execution gate",)
    assert calls == []


def test_future_environment_observation_beyond_skew_is_rejected(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)

    gate = _gate(current + timedelta(seconds=3))

    assert not gate.allowed
    assert "operational: environment observation is ahead of evaluation" in gate.reasons


def test_environment_observation_within_clock_skew_is_allowed(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)

    gate = _gate(current + timedelta(seconds=1))

    assert gate.allowed
    assert gate.reasons == ()


def test_naive_evaluation_clock_fails_closed(monkeypatch):
    current = datetime.now()
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)

    gate = _gate(current.replace(tzinfo=timezone.utc))

    assert not gate.allowed
    assert gate.reasons == (
        "safety evaluation error: now must be timezone-aware",)


def test_editing_environment_gate_timing_invalidates_it(monkeypatch):
    current = datetime.now(timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)
    gate = _gate(current)
    object.__setattr__(gate, "_max_age_seconds", 60.0)

    result, calls = _attempt(
        gate, current + timedelta(seconds=1), "edited-gate", monkeypatch)

    assert not result.executed
    assert calls == []
