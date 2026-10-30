from risk.trade_gates import (
    GateResult,
    all_gates,
    cooldown_gate,
    daily_loss_gate,
    duplicate_gate,
    spread_gate,
    volatility_gate,
)


def test_spread_fails_closed_when_missing():
    assert not spread_gate(None, 30).allowed


def test_spread_rejects_wide_market():
    assert not spread_gate(31, 30).allowed


def test_volatility_bounds():
    assert not volatility_gate(0, 1, 10).allowed
    assert volatility_gate(5, 1, 10).allowed
    assert not volatility_gate(11, 1, 10).allowed


def test_daily_loss_locks_at_limit():
    assert not daily_loss_gate(-100, 100).allowed
    assert daily_loss_gate(-99.99, 100).allowed


def test_cooldown_and_duplicate():
    assert not cooldown_gate(True).allowed
    assert cooldown_gate(False).allowed
    assert not duplicate_gate(True).allowed
    assert duplicate_gate(False).allowed


def test_all_gates_short_circuits():
    result = all_gates(GateResult(True, 'ok'), GateResult(False, 'blocked'))
    assert result == GateResult(False, 'blocked')
