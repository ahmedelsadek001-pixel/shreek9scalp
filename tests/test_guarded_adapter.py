from __future__ import annotations

import ast
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

import pytest

from execution.execution_gate import (
    ExecutionGateDecision, evaluate_environment_gate, evaluate_execution_gate,
)
from execution.broker_safety import BrokerSafetyPolicy
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.reconciliation import ExecutionReport, OrderIntent
from execution.recovery import RecoveryDecision, RecoveryState, ShadowRecovery
from execution.quote_safety import evaluate_quote_safety
from execution.idempotency import IdempotencyLedger
from execution.shadow import ShadowExecution
from core.enums import Direction
from security.release_security_gate import scan_source


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DIRS = ("ai", "config", "core", "execution", "market", "paper_trading", "research", "risk", "utils")
COMPAT_PATH = Path("utils/mt5_compat.py")
GUARDED_PATH = Path("execution/guarded_adapter.py")
DEMO_TRANSPORT_PATH = Path("execution/mt5_demo_transport.py")


def _ready_gate(
    recovery: RecoveryDecision | None = None, *,
    symbol: str = "XAUUSD", volume: float = 0.03,
) -> ExecutionGateDecision:
    now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(now, now, now, True, True),
        broker_policy=BrokerSafetyPolicy(frozenset({"XAUUSD", "EURUSD"}), 1.0, 0.01, 1.0, 0.5),
        symbol=symbol, spread=0.2, volume=volume, slippage=0.1,
        recovery=recovery or RecoveryDecision(RecoveryState.CONNECTED, True, "ready"),
        kill_switch_active=False,
    )


def _intent() -> OrderIntent:
    return OrderIntent("ORD-001", "XAUUSD", Direction.BUY, 0.03, 2500.0)


def _safe_quote(intent: OrderIntent | None = None):
    price = (intent or _intent()).expected_price
    now = datetime.now(timezone.utc)
    return evaluate_quote_safety(
        quote_time=now, now=now, intended_price=price,
        market_price=price, max_age_seconds=2,
        max_deviation_points=3, point_size=0.01,
    )


def test_rejected_gate_never_invokes_executor() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))
    result = adapter.execute(evaluate_execution_gate(operational=(True, ()), broker=(True, ()), recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"), kill_switch_active=True))
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("kill switch active",)
    assert calls == []


def test_allowed_gate_cannot_execute_without_intent() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed") or "accepted")
    result = adapter.execute(_ready_gate())
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("unscoped execution disabled",)
    assert calls == []


def test_caller_supplied_positive_layers_cannot_invoke_transport() -> None:
    calls = []
    decision = evaluate_execution_gate(
        operational=(True, ()), broker=(True, ()),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "ready"),
        kill_switch_active=False,
    )
    assert decision.allowed
    adapter = GuardedExecutionAdapter(lambda intent: calls.append(intent), IdempotencyLedger())
    result = adapter.execute_intent(decision, _intent(), _safe_quote())
    assert not result.executed
    assert result.reasons == ("execution requires evaluated environment",)
    assert calls == []


@pytest.mark.parametrize("admitted", [
    {"symbol": "EURUSD"}, {"volume": 0.04},
])
def test_environment_admission_is_bound_to_intent(admitted) -> None:
    calls = []
    adapter = GuardedExecutionAdapter(lambda intent: calls.append(intent), IdempotencyLedger())
    result = adapter.execute_intent(_ready_gate(**admitted), _intent(), _safe_quote())
    assert not result.executed
    assert result.reasons == ("evaluated environment does not match intent",)
    assert calls == []


def test_fabricated_allowed_gate_is_rejected_and_never_invokes_executor() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))
    result = adapter.execute(ExecutionGateDecision(True, ()))
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("execution gate decision not issued by execution gate",)
    assert calls == []


def test_cloned_rejected_gate_cannot_bypass_kill_switch() -> None:
    calls = []
    rejected = evaluate_execution_gate(
        operational=(True, ()), broker=(True, ()),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "ready"),
        kill_switch_active=True,
    )
    cloned = replace(rejected, allowed=True, reasons=())
    adapter = GuardedExecutionAdapter(
        lambda intent: calls.append(intent), IdempotencyLedger(),
    )
    result = adapter.execute_intent(cloned, _intent(), _safe_quote())
    assert not result.executed
    assert result.reasons == ("execution gate decision not issued by execution gate",)
    assert calls == []


def test_in_place_modified_gate_is_rejected() -> None:
    decision = evaluate_execution_gate(
        operational=(True, ()), broker=(True, ()),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "ready"),
        kill_switch_active=True,
    )
    object.__setattr__(decision, "allowed", True)
    object.__setattr__(decision, "reasons", ())
    adapter = GuardedExecutionAdapter(lambda intent: None, IdempotencyLedger())
    result = adapter.execute_intent(decision, _intent(), _safe_quote())
    assert not result.executed
    assert result.reasons == ("execution gate decision not issued by execution gate",)


def test_malformed_gate_is_fail_closed() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))
    result = adapter.execute(object())
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("execution gate decision not issued by execution gate",)
    assert calls == []


def test_internally_inconsistent_allowed_gate_is_fail_closed() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))
    decision = evaluate_execution_gate(operational=(True, ("unexpected reason",)), broker=(True, ()), recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"), kill_switch_active=False)
    result = adapter.execute(decision)
    assert result.executed is False
    assert result.result is None
    assert "internally inconsistent" in result.reasons[0]
    assert calls == []


def test_executor_failure_is_reported_without_retry() -> None:
    calls: list[str] = []

    def fail(_intent: OrderIntent) -> None:
        calls.append("executed")
        raise RuntimeError("transport failure")

    adapter = GuardedExecutionAdapter(fail, IdempotencyLedger())
    result = adapter.execute_intent(_ready_gate(), _intent(), _safe_quote())
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("downstream execution failed: transport failure",)
    assert calls == ["executed"]


def test_intent_aware_execution_passes_exact_identity_to_executor() -> None:
    received: list[OrderIntent] = []
    adapter = GuardedExecutionAdapter(lambda intent: received.append(intent) or intent.order_id, IdempotencyLedger())
    intent = _intent()
    result = adapter.execute_intent(_ready_gate(), intent, _safe_quote(intent))
    assert result.executed is True
    assert result.result == "ORD-001"
    assert received == [intent]
    assert received[0] is intent


def test_intent_aware_execution_rejects_malformed_intent_without_transport() -> None:
    calls: list[object] = []
    adapter = GuardedExecutionAdapter(lambda intent: calls.append(intent))
    result = adapter.execute_intent(_ready_gate(), object())
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("order intent malformed",)
    assert calls == []


@pytest.mark.parametrize("changes", [
    {"volume": float("nan")}, {"volume": 0.0},
    {"volume": True}, {"expected_price": float("inf")},
    {"direction": Direction.UNKNOWN}, {"direction": "BUY"},
])
def test_intent_aware_execution_rejects_invalid_economics_and_direction(changes) -> None:
    calls = []
    intent = replace(_intent(), **changes)
    adapter = GuardedExecutionAdapter(lambda received: calls.append(received), IdempotencyLedger())
    result = adapter.execute_intent(_ready_gate(), intent, _safe_quote())
    assert not result.executed
    assert calls == []


def test_intent_aware_rejected_gate_never_reaches_transport() -> None:
    calls: list[OrderIntent] = []
    adapter = GuardedExecutionAdapter(lambda intent: calls.append(intent))
    rejected = evaluate_execution_gate(operational=(True, ()), broker=(True, ()), recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"), kill_switch_active=True)
    result = adapter.execute_intent(rejected, _intent())
    assert result.executed is False
    assert result.reasons == ("kill switch active",)
    assert calls == []


def test_recovery_pending_order_blocks_guarded_execution_until_reconciled() -> None:
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    intent = _intent()
    shadow.submit_intent(intent)
    adapter = GuardedExecutionAdapter(lambda received: received.order_id, IdempotencyLedger())

    blocked_gate = evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=recovery.admission(),
        kill_switch_active=False,
    )
    blocked = adapter.execute_intent(blocked_gate, intent)
    assert blocked.executed is False
    assert blocked.result is None
    assert "recovery: execution channel is not ready" in blocked.reasons

    shadow.observe(ExecutionReport(intent.order_id, intent.symbol, intent.direction, intent.volume, intent.expected_price))
    ready_gate = _ready_gate(recovery.admission())
    admitted = adapter.execute_intent(ready_gate, intent, _safe_quote(intent))
    assert admitted.executed is True
    assert admitted.result == intent.order_id


def test_recovery_transition_blocks_execution_until_clean_recovery() -> None:
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    adapter = GuardedExecutionAdapter(lambda received: received.order_id, IdempotencyLedger())
    intent = _intent()

    recovery.disconnect()
    assert recovery.begin_recovery().state is RecoveryState.RECOVERING
    blocked = adapter.execute_intent(
        _ready_gate(recovery.admission()),
        intent,
    )
    assert blocked.executed is False
    assert blocked.result is None
    assert blocked.reasons == ("recovery: execution channel is not ready",)

    assert recovery.complete_recovery().can_submit
    admitted = adapter.execute_intent(
        _ready_gate(recovery.admission()),
        intent, _safe_quote(intent),
    )
    assert admitted.executed is True
    assert admitted.result == intent.order_id


def test_non_callable_executor_rejected() -> None:
    with pytest.raises(TypeError, match="executor must be callable"):
        GuardedExecutionAdapter(None)  # type: ignore[arg-type]


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in PRODUCTION_DIRS:
        files.extend((ROOT / directory).rglob("*.py"))
    return files


def test_no_direct_mt5_import_outside_compatibility_boundary() -> None:
    violations: list[str] = []
    for path in _production_python_files():
        if path.relative_to(ROOT) == COMPAT_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "MetaTrader5" or alias.name.startswith("MetaTrader5.") for alias in node.names):
                violations.append(str(path.relative_to(ROOT)))
            elif isinstance(node, ast.ImportFrom) and (node.module == "MetaTrader5" or (node.module and node.module.startswith("MetaTrader5."))):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_no_direct_order_transport_call_outside_reviewed_boundaries() -> None:
    violations: list[str] = []
    forbidden = {"order_send", "send_order", "place_order", "submit_order"}
    for path in _production_python_files():
        relative = path.relative_to(ROOT)
        if relative == GUARDED_PATH:
            continue
        content = path.read_text(encoding="utf-8")
        if relative == DEMO_TRANSPORT_PATH:
            # This module is only exempt when the static release gate accepts
            # the exact reviewed bytes; editing it fails this test too.
            assert not scan_source(str(relative), content)
            continue
        tree = ast.parse(content, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.lower() in forbidden:
                violations.append(f"{relative}:{node.lineno}")
    assert violations == []


def test_no_direct_guarded_adapter_entrypoint_outside_adapter() -> None:
    """Keep the guarded adapter as the sole production submission boundary."""
    violations: list[str] = []
    forbidden = {"execute_intent", "execute_intent_strict"}
    for path in _production_python_files():
        relative = path.relative_to(ROOT)
        if relative == GUARDED_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden:
                violations.append(f"{relative}:{node.lineno}")
    assert violations == []


def test_safety_and_promotion_gates_have_no_transport_authority() -> None:
    """Evidence gates must stay pure policy code, never broker adapters."""
    violations: list[str] = []
    protected = (ROOT / "execution/safety_gate.py", ROOT / "core/promotion_gate.py")
    for path in protected:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "MetaTrader5" or alias.name.startswith("MetaTrader5.") for alias in node.names):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:MetaTrader5")
            elif isinstance(node, ast.ImportFrom) and (node.module == "MetaTrader5" or (node.module and node.module.startswith("MetaTrader5."))):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:MetaTrader5")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"order_send", "send_order", "place_order", "submit_order"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.func.attr}")
    assert violations == []


def test_idempotency_ledger_blocks_second_transport_attempt() -> None:
    from execution.idempotency import IdempotencyLedger
    calls: list[str] = []
    ledger = IdempotencyLedger()
    adapter = GuardedExecutionAdapter(lambda intent: calls.append(intent.order_id) or "sent", ledger)
    first = adapter.execute_intent(_ready_gate(), _intent(), _safe_quote())
    second = adapter.execute_intent(_ready_gate(), _intent(), _safe_quote())
    assert first.executed is True
    assert second.executed is False
    assert "idempotency rejected" in second.reasons[0]
    assert calls == ["ORD-001"]


def test_transport_exception_marks_intent_unknown_and_blocks_retry() -> None:
    from execution.idempotency import IdempotencyLedger, SubmissionState
    ledger = IdempotencyLedger()
    calls: list[str] = []
    def fail(intent):
        calls.append(intent.order_id)
        raise TimeoutError("broker timeout")
    adapter = GuardedExecutionAdapter(fail, ledger)
    first = adapter.execute_intent(_ready_gate(), _intent(), _safe_quote())
    assert first.executed is False
    assert ledger.get("ORD-001").state is SubmissionState.UNKNOWN
    second = adapter.execute_intent(_ready_gate(), _intent(), _safe_quote())
    assert second.executed is False
    assert calls == ["ORD-001"]


def test_missing_ledger_blocks_transport() -> None:
    calls = []
    adapter = GuardedExecutionAdapter(lambda intent: calls.append(intent.order_id))
    blocked = adapter.execute_intent(_ready_gate(), _intent(), _safe_quote())
    assert not blocked.executed
    assert blocked.reasons == ("idempotency ledger required",)
    blocked = adapter.execute_intent(_ready_gate(), _intent(), _safe_quote())
    assert not blocked.executed
    assert calls == []
