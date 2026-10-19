"""Quote timing evidence must remain immutable after safety evaluation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

import pytest

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


class MutableOffset(tzinfo):
    def __init__(self, offset: timedelta) -> None:
        self.offset = offset

    def utcoffset(self, _value: datetime | None) -> timedelta:
        return self.offset

    def dst(self, _value: datetime | None) -> timedelta:
        return timedelta(0)


class MissingOffset(tzinfo):
    def utcoffset(self, _value: datetime | None) -> None:
        return None

    def dst(self, _value: datetime | None) -> timedelta:
        return timedelta(0)


class RaisingOffset(tzinfo):
    def utcoffset(self, _value: datetime | None) -> timedelta:
        raise RuntimeError("untrusted timezone")

    def dst(self, _value: datetime | None) -> timedelta:
        return timedelta(0)


def _quote(quote_time: datetime, now: datetime, *, max_age: float = 2.0):
    return evaluate_quote_safety(
        symbol="XAUUSD", direction=Direction.BUY,
        quote_time=quote_time, now=now,
        intended_price=2500.0, market_price=2500.0,
        max_age_seconds=max_age, max_deviation_points=3,
        point_size=.01,
    )


def _gate(now: datetime):
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(
            now, now, now, True, True),
        broker_policy=BrokerSafetyPolicy(
            frozenset({"XAUUSD"}), 1.0, .01, 1.0, .5),
        symbol="XAUUSD", spread=.2, volume=.03, slippage=.1,
        kill_switch_active=False,
        recovery=ShadowRecovery(ShadowExecution()).admission(),
    )


def test_quote_decision_stores_independent_utc_timestamp_snapshots():
    offset = MutableOffset(timedelta(hours=2))
    supplied = datetime(2026, 10, 3, 8, 0, tzinfo=offset)

    decision = _quote(supplied, supplied)

    assert decision.allowed
    assert decision.quote_time is not supplied
    assert decision.evaluated_at is not supplied
    assert decision.quote_time == datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)
    assert decision.evaluated_at == datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)
    assert decision.quote_time.tzinfo is timezone.utc
    assert decision.evaluated_at.tzinfo is timezone.utc
    offset.offset = timedelta(hours=5)
    assert decision.quote_time == datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)
    assert decision.evaluated_at == datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)


def test_mutated_timezone_cannot_revive_expired_quote(monkeypatch):
    base = datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(execution_gate, "utc_now", lambda: base)
    gate = _gate(base)
    offset = MutableOffset(timedelta(0))
    supplied = datetime(2026, 10, 3, 5, 0, tzinfo=offset)
    quote = _quote(supplied, supplied, max_age=.1)
    offset.offset = -timedelta(seconds=1)
    monkeypatch.setattr(
        guarded_adapter, "utc_now", lambda: base + timedelta(seconds=1))
    calls: list[str] = []
    intent = OrderIntent(
        "mutable-timezone", "XAUUSD", Direction.BUY, .03, 2500.0)

    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.order_id) or "offline-only",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)

    assert not result.executed
    assert result.reasons == ("quote expired before submission",)
    assert calls == []


@pytest.mark.parametrize("bad_timezone", [MissingOffset(), RaisingOffset()])
def test_invalid_timezone_offset_fails_closed(bad_timezone):
    supplied = datetime(2026, 10, 3, 5, 0, tzinfo=bad_timezone)

    decision = _quote(supplied, supplied)

    assert not decision.allowed
    assert decision.reason == "timestamps must be timezone-aware"


def test_distinct_timezone_offsets_preserve_the_absolute_instant():
    quote_time = datetime(
        2026, 10, 3, 8, 0, tzinfo=timezone(timedelta(hours=2)))
    now = datetime(
        2026, 10, 3, 1, 0, 1, tzinfo=timezone(timedelta(hours=-5)))

    decision = _quote(quote_time, now)

    assert decision.allowed
    assert decision.quote_time == datetime(
        2026, 10, 3, 6, 0, tzinfo=timezone.utc)
    assert decision.evaluated_at == datetime(
        2026, 10, 3, 6, 0, 1, tzinfo=timezone.utc)
