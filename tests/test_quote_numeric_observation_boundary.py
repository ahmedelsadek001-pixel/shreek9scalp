"""Quote numerics cannot run caller-owned conversion code."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.enums import Direction
from execution.broker_safety import BrokerSafetyPolicy
from execution.execution_gate import evaluate_environment_gate
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.idempotency import IdempotencyLedger
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.quote_safety import evaluate_quote_safety, is_quote_issued
from execution.reconciliation import OrderIntent
from execution.recovery import ShadowRecovery
from execution.shadow import ShadowExecution


class CoercedFloat(float):
    def __new__(cls, raw: float, replacement: float):
        value = super().__new__(cls, raw)
        value.replacement = replacement
        return value

    def __float__(self) -> float:
        return self.replacement


class CoercedInt(int):
    def __new__(cls, raw: int, replacement: float):
        value = super().__new__(cls, raw)
        value.replacement = replacement
        return value

    def __float__(self) -> float:
        return self.replacement


class RaisingFloat(float):
    def __float__(self) -> float:
        raise RuntimeError("caller-controlled numeric conversion")


SAFE_VALUES = {
    "intended_price": 2500.0,
    "market_price": 2500.0,
    "max_age_seconds": 2.0,
    "max_deviation_points": 3.0,
    "point_size": 0.01,
}


def _quote(**overrides):
    now = datetime.now(timezone.utc)
    values = dict(SAFE_VALUES)
    values.update(overrides)
    return evaluate_quote_safety(
        symbol="XAUUSD",
        direction=Direction.BUY,
        quote_time=now,
        now=now,
        **values,
    )


def _attempt(quote):
    now = datetime.now(timezone.utc)
    gate = evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(
            now, now, now, True, True),
        broker_policy=BrokerSafetyPolicy(
            frozenset({"XAUUSD"}), 1.0, 0.01, 1.0, 0.5),
        symbol="XAUUSD",
        spread=0.2,
        volume=0.03,
        slippage=0.1,
        kill_switch_active=False,
        recovery=ShadowRecovery(ShadowExecution()).admission(),
    )
    intent = OrderIntent(
        "QUOTE-NUMERIC-OBSERVATION",
        "XAUUSD",
        Direction.BUY,
        0.03,
        2500.0,
    )
    calls: list[str] = []
    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.order_id) or "offline-accepted",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)
    return result, calls


@pytest.mark.parametrize("numeric_type", [CoercedFloat, CoercedInt])
@pytest.mark.parametrize("field,replacement", SAFE_VALUES.items())
def test_coerced_quote_numeric_cannot_reach_transport(
    numeric_type, field: str, replacement: float,
):
    quote = _quote(**{field: numeric_type(-1, replacement)})

    result, calls = _attempt(quote)

    assert not quote.allowed
    assert quote.reason == "quote safety inputs must be numeric"
    assert is_quote_issued(quote)
    assert not result.executed
    assert result.reasons == (
        "quote safety: quote safety inputs must be numeric",
    )
    assert calls == []


@pytest.mark.parametrize("field", SAFE_VALUES)
def test_raising_quote_numeric_becomes_an_issued_denial(field: str):
    quote = _quote(**{field: RaisingFloat(SAFE_VALUES[field])})

    assert not quote.allowed
    assert quote.reason == "quote safety inputs must be numeric"
    assert is_quote_issued(quote)


def test_exact_quote_numerics_retain_offline_control_path():
    quote = _quote()

    result, calls = _attempt(quote)

    assert quote.allowed
    assert result.executed
    assert calls == ["QUOTE-NUMERIC-OBSERVATION"]
