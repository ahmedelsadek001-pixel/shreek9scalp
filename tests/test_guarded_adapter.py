import pytest

from execution.execution_gate import ExecutionGateDecision, evaluate_execution_gate
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.recovery import RecoveryDecision, RecoveryState


def _ready_gate() -> ExecutionGateDecision:
    return evaluate_execution_gate(
        operational=(True, ()),
        broker=(True, ()),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"),
        kill_switch_active=False,
    )


def test_rejected_gate_never_invokes_executor() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))

    result = adapter.execute(
        evaluate_execution_gate(
            operational=(True, ()),
            broker=(True, ()),
            recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"),
            kill_switch_active=True,
        )
    )

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

    decision = evaluate_execution_gate(
        operational=(True, ("unexpected reason",)),
        broker=(True, ()),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "execution channel available"),
        kill_switch_active=False,
    )
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


def test_non_callable_executor_rejected() -> None:
    with pytest.raises(TypeError, match="executor must be callable"):
        GuardedExecutionAdapter(None)  # type: ignore[arg-type]
