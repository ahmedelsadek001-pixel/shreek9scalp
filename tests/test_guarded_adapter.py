import pytest

from execution.execution_gate import ExecutionGateDecision
from execution.guarded_adapter import GuardedExecutionAdapter


def test_rejected_gate_never_invokes_executor() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))

    result = adapter.execute(ExecutionGateDecision(False, ("kill switch active",)))

    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("kill switch active",)
    assert calls == []


def test_allowed_gate_invokes_executor_once() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed") or "accepted")

    result = adapter.execute(ExecutionGateDecision(True, ()))

    assert result.executed is True
    assert result.result == "accepted"
    assert result.reasons == ()
    assert calls == ["executed"]


def test_malformed_gate_is_fail_closed() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))

    result = adapter.execute(object())

    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("execution gate decision malformed",)
    assert calls == []


def test_internally_inconsistent_allowed_gate_is_fail_closed() -> None:
    calls: list[str] = []
    adapter = GuardedExecutionAdapter(lambda: calls.append("executed"))

    result = adapter.execute(ExecutionGateDecision(True, ("unexpected reason",)))

    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("execution gate decision internally inconsistent",)
    assert calls == []


def test_executor_failure_is_reported_without_retry() -> None:
    calls: list[str] = []

    def fail() -> None:
        calls.append("executed")
        raise RuntimeError("transport failure")

    adapter = GuardedExecutionAdapter(fail)
    result = adapter.execute(ExecutionGateDecision(True, ()))

    assert result.executed is False
    assert result.result is None
    assert result.reasons == ("downstream execution failed: transport failure",)
    assert calls == ["executed"]


def test_non_callable_executor_rejected() -> None:
    with pytest.raises(TypeError, match="executor must be callable"):
        GuardedExecutionAdapter(None)  # type: ignore[arg-type]
