import pytest

from risk.risk_state import RiskState, RiskStateMachine


def test_losses_enter_cooldown_then_kill():
    machine = RiskStateMachine(max_consecutive_losses=3)
    machine.record_result(-1)
    assert machine.state is RiskState.COOLDOWN
    assert not machine.can_open()
    machine.reset()
    machine.record_result(-1)
    machine.record_result(-1)
    machine.record_result(-1)
    assert machine.state is RiskState.KILLED
    assert not machine.can_open()


def test_win_arms_after_non_killed_cooldown():
    machine = RiskStateMachine(max_consecutive_losses=3)
    machine.record_result(-1)
    machine.record_result(1)
    assert machine.state is RiskState.ARMED
    assert machine.consecutive_losses == 0


def test_killed_state_requires_explicit_reset():
    machine = RiskStateMachine(max_consecutive_losses=1)
    machine.record_result(-1)
    assert machine.state is RiskState.KILLED
    with pytest.raises(RuntimeError):
        machine.arm()
    machine.reset()
    assert machine.can_open()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"state": "ARMED"},
        {"consecutive_losses": True},
        {"consecutive_losses": -1},
        {"consecutive_losses": 1.5},
        {"max_consecutive_losses": True},
        {"max_consecutive_losses": 0},
        {"max_consecutive_losses": -1},
        {"max_consecutive_losses": 2.5},
    ],
    ids=["string-state", "bool-loss-count", "negative-loss-count", "float-loss-count",
         "bool-limit", "zero-limit", "negative-limit", "float-limit"],
)
def test_invalid_initial_state_is_rejected(kwargs):
    with pytest.raises(ValueError):
        RiskStateMachine(**kwargs)


@pytest.mark.parametrize(
    "pnl",
    [None, "1", True, float("nan"), float("inf"), float("-inf"), 10**10000],
    ids=["none", "numeric-string", "boolean", "nan", "positive-infinity",
         "negative-infinity", "oversized-integer"],
)
def test_invalid_result_is_rejected_without_mutating_state(pnl):
    machine = RiskStateMachine(state=RiskState.COOLDOWN, consecutive_losses=1)
    with pytest.raises(ValueError, match="finite number"):
        machine.record_result(pnl)
    assert machine.state is RiskState.COOLDOWN
    assert machine.consecutive_losses == 1
