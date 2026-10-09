"""Safety timestamps must not execute caller-owned datetime subclass code."""
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


class RewrittenDateTime(datetime):
    """Retain one instant while reporting another through Python properties."""

    def __new__(
        cls,
        actual: datetime,
        reported: datetime,
    ) -> "RewrittenDateTime":
        value = super().__new__(
            cls,
            actual.year,
            actual.month,
            actual.day,
            actual.hour,
            actual.minute,
            actual.second,
            actual.microsecond,
            tzinfo=actual.tzinfo,
            fold=actual.fold,
        )
        value.reported = reported
        return value

    @property
    def year(self) -> int:
        return self.reported.year

    @property
    def month(self) -> int:
        return self.reported.month

    @property
    def day(self) -> int:
        return self.reported.day

    @property
    def hour(self) -> int:
        return self.reported.hour

    @property
    def minute(self) -> int:
        return self.reported.minute

    @property
    def second(self) -> int:
        return self.reported.second

    @property
    def microsecond(self) -> int:
        return self.reported.microsecond

    def utcoffset(self) -> timedelta | None:
        return self.reported.utcoffset()


class RaisingDateTime(datetime):
    touched = False

    @property
    def year(self) -> int:
        type(self).touched = True
        raise RuntimeError("caller-owned datetime component executed")


NOW = datetime(2026, 10, 4, 0, 30, tzinfo=timezone.utc)
STALE = NOW - timedelta(hours=1)


def _quote(timestamp: datetime):
    return evaluate_quote_safety(
        symbol="XAUUSD",
        direction=Direction.BUY,
        quote_time=timestamp,
        now=NOW,
        intended_price=2500.0,
        market_price=2500.0,
        max_age_seconds=2.0,
        max_deviation_points=3.0,
        point_size=0.01,
    )


def _environment(snapshot: OperationalSnapshot):
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=snapshot,
        broker_policy=BrokerSafetyPolicy(
            frozenset({"XAUUSD"}), 1.0, 0.01, 1.0, 0.5),
        symbol="XAUUSD",
        spread=0.2,
        volume=0.03,
        slippage=0.1,
        kill_switch_active=False,
        recovery=ShadowRecovery(ShadowExecution()).admission(),
    )


def _execute(gate, quote):
    calls: list[str] = []
    intent = OrderIntent(
        "timestamp-boundary", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.order_id) or "offline-only",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)
    return result, calls


def test_quote_datetime_subclass_cannot_rewrite_a_stale_instant(monkeypatch):
    monkeypatch.setattr(execution_gate, "utc_now", lambda: NOW)
    monkeypatch.setattr(guarded_adapter, "utc_now", lambda: NOW)
    gate = _environment(OperationalSnapshot(NOW, NOW, NOW, True, True))
    quote = _quote(RewrittenDateTime(STALE, NOW))

    result, calls = _execute(gate, quote)

    assert quote.allowed is False
    assert result.executed is False
    assert calls == []


def test_operational_datetime_subclass_cannot_rewrite_stale_evidence(
    monkeypatch,
):
    monkeypatch.setattr(execution_gate, "utc_now", lambda: NOW)
    monkeypatch.setattr(guarded_adapter, "utc_now", lambda: NOW)
    rewritten = RewrittenDateTime(STALE, NOW)
    gate = _environment(OperationalSnapshot(
        rewritten, rewritten, rewritten, True, True))

    result, calls = _execute(gate, _quote(NOW))

    assert gate.allowed is False
    assert result.executed is False
    assert calls == []


def test_quote_datetime_subclass_code_is_not_executed():
    RaisingDateTime.touched = False
    supplied = RaisingDateTime(
        NOW.year, NOW.month, NOW.day, NOW.hour, NOW.minute,
        tzinfo=timezone.utc,
    )

    decision = _quote(supplied)

    assert decision.allowed is False
    assert RaisingDateTime.touched is False


def test_operational_datetime_subclass_code_is_not_executed(monkeypatch):
    RaisingDateTime.touched = False
    supplied = RaisingDateTime(
        NOW.year, NOW.month, NOW.day, NOW.hour, NOW.minute,
        tzinfo=timezone.utc,
    )
    monkeypatch.setattr(execution_gate, "utc_now", lambda: NOW)

    decision = _environment(OperationalSnapshot(
        supplied, supplied, supplied, True, True))

    assert decision.allowed is False
    assert RaisingDateTime.touched is False


def test_exact_builtin_current_timestamps_retain_offline_control(monkeypatch):
    monkeypatch.setattr(execution_gate, "utc_now", lambda: NOW)
    monkeypatch.setattr(guarded_adapter, "utc_now", lambda: NOW)
    gate = _environment(OperationalSnapshot(NOW, NOW, NOW, True, True))

    result, calls = _execute(gate, _quote(NOW))

    assert gate.allowed is True
    assert result.executed is True
    assert calls == ["timestamp-boundary"]


def test_exact_builtin_stale_timestamps_remain_blocked(monkeypatch):
    monkeypatch.setattr(execution_gate, "utc_now", lambda: NOW)

    quote = _quote(STALE)
    gate = _environment(OperationalSnapshot(
        STALE, STALE, STALE, True, True))

    assert quote.allowed is False
    assert gate.allowed is False
