"""Operational evidence must be evaluated from a stable snapshot."""
from datetime import datetime, timedelta, timezone, tzinfo

from core.enums import Direction
from execution import execution_gate, guarded_adapter
from execution.broker_safety import BrokerSafetyPolicy
from execution.execution_gate import evaluate_environment_gate, is_gate_issued
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.idempotency import IdempotencyLedger
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.quote_safety import evaluate_quote_safety
from execution.reconciliation import OrderIntent
from execution.recovery import ShadowRecovery
from execution.shadow import ShadowExecution


class SwitchingOffset(tzinfo):
    """Return a safe-looking offset once, then change the represented instant."""

    def __init__(self) -> None:
        self.calls = 0

    def utcoffset(self, _value: datetime | None) -> timedelta:
        self.calls += 1
        if self.calls == 1:
            return timedelta(0)
        return -timedelta(hours=1)

    def dst(self, _value: datetime | None) -> timedelta:
        return timedelta(0)


class RaisingOffset(tzinfo):
    def utcoffset(self, _value: datetime | None) -> timedelta:
        raise RuntimeError("untrusted operational timezone")

    def dst(self, _value: datetime | None) -> timedelta:
        return timedelta(0)


class RaisingSnapshot(OperationalSnapshot):
    def __getattribute__(self, name: str):
        if name == "connected":
            raise RuntimeError("untrusted snapshot subclass")
        return super().__getattribute__(name)


def broker_policy() -> BrokerSafetyPolicy:
    return BrokerSafetyPolicy(
        allowed_symbols=frozenset({"XAUUSD"}),
        max_spread=1.0,
        min_volume=0.01,
        max_volume=1.0,
        max_slippage=0.5,
    )


def environment_gate(snapshot: OperationalSnapshot):
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=snapshot,
        broker_policy=broker_policy(),
        symbol="XAUUSD",
        spread=0.2,
        volume=0.03,
        slippage=0.1,
        kill_switch_active=False,
        recovery=ShadowRecovery(ShadowExecution()).admission(),
    )


def test_changing_offsets_cannot_revive_stale_operational_evidence(monkeypatch):
    current = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
    stale_wall_time = datetime(2026, 10, 3, 16, 0)
    snapshot = OperationalSnapshot(
        observed_at=stale_wall_time.replace(tzinfo=SwitchingOffset()),
        quote_time=stale_wall_time.replace(tzinfo=SwitchingOffset()),
        heartbeat_at=stale_wall_time.replace(tzinfo=SwitchingOffset()),
        connected=True,
        trading_enabled=True,
    )
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)

    gate = environment_gate(snapshot)
    intent = OrderIntent(
        "stale-operational-snapshot", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    quote = evaluate_quote_safety(
        symbol=intent.symbol,
        direction=intent.direction,
        quote_time=current,
        now=current,
        intended_price=intent.expected_price,
        market_price=intent.expected_price,
        max_age_seconds=2.0,
        max_deviation_points=3.0,
        point_size=0.01,
    )
    calls: list[str] = []
    monkeypatch.setattr(guarded_adapter, "utc_now", lambda: current)

    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.order_id) or "offline-only",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)

    assert gate.allowed is False
    assert "operational: environment observation is stale" in gate.reasons
    assert "operational: quote is stale" in gate.reasons
    assert "operational: heartbeat is stale" in gate.reasons
    assert result.executed is False
    assert calls == []


def test_raising_timezone_becomes_an_issued_denial(monkeypatch):
    current = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
    supplied = datetime(2026, 10, 3, 17, 0, tzinfo=RaisingOffset())
    snapshot = OperationalSnapshot(
        supplied, supplied, supplied, True, True)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)

    decision = environment_gate(snapshot)

    assert decision.allowed is False
    assert decision.reasons == (
        "operational: observed_at and quote_time must be timezone-aware",
    )
    assert is_gate_issued(decision) is True


def test_snapshot_subclass_cannot_execute_custom_attribute_code(monkeypatch):
    current = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
    snapshot = RaisingSnapshot(
        current, current, current, True, True)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)

    decision = environment_gate(snapshot)

    assert decision.allowed is False
    assert decision.reasons == (
        "safety evaluation error: snapshot must be OperationalSnapshot "
        "(exact type required)",
    )
    assert is_gate_issued(decision) is True


def test_exact_stable_snapshot_retains_authorized_control(monkeypatch):
    current = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
    snapshot = OperationalSnapshot(
        current, current, current, True, True)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: current)

    decision = environment_gate(snapshot)

    assert decision.allowed is True
    assert decision.reasons == ()
    assert is_gate_issued(decision) is True
