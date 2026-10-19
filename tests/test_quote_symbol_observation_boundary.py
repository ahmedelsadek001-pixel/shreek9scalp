"""Quote observations cannot redefine symbol identity at submission."""
from __future__ import annotations

from datetime import datetime, timezone

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


class SpoofedQuoteSymbol(str):
    """Claim equality with an intent while retaining another symbol value."""

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False


class RaisingStripSymbol(str):
    def strip(self, *args, **kwargs):
        raise RuntimeError("caller-controlled quote symbol")


def _gate_and_intent():
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
        "QUOTE-OBSERVED-SYMBOL", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    return gate, intent


def _quote(symbol: object):
    now = datetime.now(timezone.utc)
    return evaluate_quote_safety(
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


def _attempt(quote):
    gate, intent = _gate_and_intent()
    calls: list[str] = []
    result = GuardedExecutionAdapter(
        lambda item: calls.append(item.symbol) or "offline-accepted",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, quote)
    return result, calls


def test_quote_symbol_spoof_cannot_reach_transport():
    quote = _quote(SpoofedQuoteSymbol("BTCUSD"))

    result, calls = _attempt(quote)

    assert not quote.allowed
    assert quote.reason == "quote symbol must be exact and non-empty"
    assert is_quote_issued(quote)
    assert not result.executed
    assert result.reasons == (
        "quote safety: quote symbol must be exact and non-empty",
    )
    assert calls == []


def test_raising_quote_symbol_method_becomes_an_issued_denial():
    quote = _quote(RaisingStripSymbol("XAUUSD"))

    assert not quote.allowed
    assert quote.reason == "quote symbol must be exact and non-empty"
    assert is_quote_issued(quote)


def test_exact_quote_symbol_retains_offline_control_path():
    quote = _quote("XAUUSD")

    result, calls = _attempt(quote)

    assert quote.allowed
    assert result.executed
    assert calls == ["XAUUSD"]
