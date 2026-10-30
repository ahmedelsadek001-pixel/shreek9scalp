import pytest

from risk.risk_state import RiskState, RiskStateMachine


def test_losses_enter_cooldown_then_kill():
    machine = RiskStateMachine(max_consecutive_losses=3)
    machine.record_result(-1)
    assert machine.state is RiskState.COOLDOWN
    assert not machine.can_open()
    machine.reset(operator_approved=True, reason="reviewed cooldown")
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
    machine.reset(operator_approved=True, reason="operator reviewed kill")
    assert machine.can_open()


def test_reset_without_explicit_approval_fails_closed_and_preserves_kill():
    machine = RiskStateMachine(max_consecutive_losses=1)
    machine.record_result(-1)
    with pytest.raises(RuntimeError, match="explicit operator approval"):
        machine.reset()
    assert machine.state is RiskState.KILLED
    assert not machine.can_open()


@pytest.mark.parametrize(
    "kwargs",
    [{"operator_approved": False, "reason": "reviewed"},
     {"operator_approved": True, "reason": ""},
     {"operator_approved": True, "reason": "   "},
     {"operator_approved": True, "reason": None}],
)
def test_reset_rejects_missing_or_malformed_approval(kwargs):
    machine = RiskStateMachine(state=RiskState.COOLDOWN, consecutive_losses=1)
    with pytest.raises((RuntimeError, ValueError)):
        machine.reset(**kwargs)
    assert machine.state is RiskState.COOLDOWN
    assert machine.consecutive_losses == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"state": "ARMED"},
        {"consecutive_losses": True},
        {"consecutive_losses": -1},
        {"consecutive_losses": 1.5},
        {"consecutive_losses": 4, "max_consecutive_losses": 3},
        {"max_consecutive_losses": True},
        {"max_consecutive_losses": 0},
        {"max_consecutive_losses": -1},
        {"max_consecutive_losses": 2.5},
    ],
    ids=["string-state", "bool-loss-count", "negative-loss-count", "float-loss-count",
         "loss-count-over-limit", "bool-limit", "zero-limit", "negative-limit", "float-limit"],
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


def test_loss_counter_saturates_at_kill_threshold():
    machine = RiskStateMachine(max_consecutive_losses=2)
    machine.record_result(-1)
    assert machine.consecutive_losses == 1
    assert machine.state is RiskState.COOLDOWN
    machine.record_result(-1)
    assert machine.consecutive_losses == 2
    assert machine.state is RiskState.KILLED
    machine.record_result(-1)
    assert machine.consecutive_losses == 2
    assert machine.state is RiskState.KILLED
    assert not machine.can_open()
