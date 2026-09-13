import ast
from pathlib import Path

import pytest

from execution.execution_gate import ExecutionGateDecision, evaluate_execution_gate
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.reconciliation import OrderIntent
from execution.recovery import RecoveryDecision, RecoveryState
from core.enums import Direction


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DIRS = ("ai", "config", "core", "execution", "market", "paper_trading", "research", "risk", "utils")
COMPAT_PATH = Path("utils/mt5_compat.py")
GUARDED_PATH = Path("execution/guarded_adapter.py")


def _ready_gate() -> ExecutionGateDecision:
    return evaluate_execution_gate(operational=(True, ()), broker=(True, ()), recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"), kill_switch_active=False)


def _intent() -> OrderIntent:
    return OrderIntent("ORD-001", "XAUUSD", Direction.BUY, 0.03, 2500.0)


def test_rejected_gate_never_invokes_executor() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))
    result = adapter.execute(evaluate_execution_gate(operational=(True, ()), broker=(True, ()), recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"), kill_switch_active=True))
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("kill switch active",)
    assert calls == []


def test_allowed_gate_invokes_executor_once() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed") or "accepted")
    result = adapter.execute(_ready_gate())
    assert result.executed is True
    assert result.result == "accepted"
    assert result.reasons == ()
    assert calls == ["executed"]


def test_fabricated_allowed_gate_is_rejected_and_never_invokes_executor() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))
    result = adapter.execute(ExecutionGateDecision(True, ()))
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("execution gate decision not issued by execution gate",)
    assert calls == []


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

    def fail() -> None:
        calls.append("executed")
        raise RuntimeError("transport failure")

    adapter = GuardedExecutionAdapter(fail)
    result = adapter.execute(_ready_gate())
    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("downstream execution failed: transport failure",)
    assert calls == ["executed"]


def test_intent_aware_execution_passes_exact_identity_to_executor() -> None:
    received: list[OrderIntent] = []
    adapter = GuardedExecutionAdapter(lambda intent: received.append(intent) or intent.order_id)
    intent = _intent()
    result = adapter.execute_intent(_ready_gate(), intent)
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


def test_intent_aware_rejected_gate_never_reaches_transport() -> None:
    calls: list[OrderIntent] = []
    adapter = GuardedExecutionAdapter(lambda intent: calls.append(intent))
    rejected = evaluate_execution_gate(operational=(True, ()), broker=(True, ()), recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"), kill_switch_active=True)
    result = adapter.execute_intent(rejected, _intent())
    assert result.executed is False
    assert result.reasons == ("kill switch active",)
    assert calls == []


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


def test_no_direct_order_transport_call_outside_guarded_adapter() -> None:
    violations: list[str] = []
    forbidden = {"order_send", "send_order", "place_order", "submit_order"}
    for path in _production_python_files():
        relative = path.relative_to(ROOT)
        if relative == GUARDED_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.lower() in forbidden:
                violations.append(f"{relative}:{node.lineno}")
    assert violations == []
