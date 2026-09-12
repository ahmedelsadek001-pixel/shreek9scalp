import pytest

from risk.kill_switch import KillScope, KillSwitch


def test_any_active_scope_blocks():
    state = KillSwitch().activate(KillScope.SYMBOL)
    assert state.is_blocked()
    assert not state.can_trade()


def test_activation_is_immutable():
    state = KillSwitch()
    blocked = state.activate(KillScope.SESSION)
    assert not state.is_blocked()
    assert blocked.session


def test_engine_scope_blocks_everything():
    assert KillSwitch().activate(KillScope.ENGINE).is_blocked()


def test_require_live_fails_closed():
    with pytest.raises(RuntimeError, match="kill switch active"):
        KillSwitch().activate(KillScope.STRATEGY).require_live()
