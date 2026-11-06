from decimal import Decimal

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


@pytest.mark.parametrize(
    "field",
    ("max_spread", "min_volume", "max_volume", "max_slippage"),
)
@pytest.mark.parametrize(
    "invalid_value",
    (True, False, "0.2", None, Decimal("0.2")),
    ids=("true", "false", "numeric-text", "none", "decimal"),
)
def test_policy_rejects_coercible_or_non_builtin_numbers(field, invalid_value):
    values = {
        "allowed_symbols": frozenset({"XAUUSD"}),
        "max_spread": 0.5,
        "min_volume": 0.01,
        "max_volume": 1.0,
        "max_slippage": 0.2,
    }
    values[field] = invalid_value

    with pytest.raises(ValueError, match="numbers"):
        BrokerSafetyPolicy(**values).validate()


def test_policy_rejects_integer_too_large_for_finite_float_validation():
    policy = BrokerSafetyPolicy(
        frozenset({"XAUUSD"}), 10**10_000, 0.01, 1.0, 0.2)

    with pytest.raises(ValueError, match="finite"):
        policy.validate()


def test_policy_accepts_plain_non_negative_ints_and_floats():
    BrokerSafetyPolicy(frozenset({"XAUUSD"}), 1, 1, 2.0, 0).validate()


@pytest.mark.parametrize("field", ("spread", "volume", "slippage"))
@pytest.mark.parametrize(
    "invalid_value",
    (True, False, "0.1", None, Decimal("0.1")),
    ids=("true", "false", "numeric-text", "none", "decimal"),
)
def test_environment_rejects_coercible_or_non_builtin_numbers(
    field, invalid_value,
):
    observations = {"spread": 0.2, "volume": 0.03, "slippage": 0.1}
    observations[field] = invalid_value

    allowed, reasons = authorize_environment(
        POLICY,
        symbol="XAUUSD",
        connected=True,
        trading_enabled=True,
        **observations,
    )

    assert allowed is False
    assert reasons == (
        "broker observations must be finite built-in numbers",
    )


def test_plain_numeric_environment_retains_authorized_control_path():
    allowed, reasons = authorize_environment(
        POLICY,
        symbol="XAUUSD",
        spread=0,
        volume=1,
        slippage=0,
        connected=True,
        trading_enabled=True,
    )

    assert allowed is True
    assert reasons == ()
