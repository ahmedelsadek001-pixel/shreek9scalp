import pytest

from execution.broker_safety import BrokerSafetyPolicy, authorize_environment


POLICY = BrokerSafetyPolicy(frozenset({"XAUUSD"}), 0.5, 0.01, 1.0, 0.2)


def test_safe_environment_authorizes():
    allowed, reasons = authorize_environment(
        POLICY, symbol="XAUUSD", spread=0.2, volume=0.03, slippage=0.1,
        connected=True, trading_enabled=True,
    )
    assert allowed is True
    assert reasons == ()


def test_disconnect_blocks():
    allowed, reasons = authorize_environment(
        POLICY, symbol="XAUUSD", spread=0.2, volume=0.03, slippage=0.1,
        connected=False, trading_enabled=True,
    )
    assert allowed is False
    assert "broker disconnected" in reasons


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        authorize_environment(BrokerSafetyPolicy(frozenset(), 0.5, 0.01, 1.0, 0.2), symbol="XAUUSD", spread=0.2, volume=0.03, slippage=0.1, connected=True, trading_enabled=True)
