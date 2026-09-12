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
