"""Policy evaluators must own the validation code used at safety boundaries."""
from datetime import datetime, timezone

import pytest

from execution.broker_safety import BrokerSafetyPolicy, authorize_environment
from execution.execution_gate import evaluate_environment_gate, is_gate_issued
from execution.operational_guard import (
    OperationalPolicy,
    OperationalSnapshot,
    evaluate_operational_readiness,
)
from execution.recovery import ShadowRecovery
from execution.shadow import ShadowExecution


class BypassOperationalPolicy(OperationalPolicy):
    def validate(self) -> None:
        """Model an untrusted subclass replacing the owning validator."""


class BypassBrokerSafetyPolicy(BrokerSafetyPolicy):
    def validate(self) -> None:
        """Model an untrusted subclass replacing the owning validator."""


def snapshot() -> OperationalSnapshot:
    observed = datetime.now(timezone.utc)
    return OperationalSnapshot(
        observed_at=observed,
        quote_time=observed,
        heartbeat_at=observed,
        connected=True,
        trading_enabled=True,
    )


def broker_policy() -> BrokerSafetyPolicy:
    return BrokerSafetyPolicy(
        allowed_symbols=frozenset({"XAUUSD"}),
        max_spread=1.0,
        min_volume=0.01,
        max_volume=1.0,
        max_slippage=0.5,
    )


def environment_gate(**overrides):
    arguments = {
        "operational_policy": OperationalPolicy(),
        "operational_snapshot": snapshot(),
        "broker_policy": broker_policy(),
        "symbol": "XAUUSD",
        "spread": 0.2,
        "volume": 0.03,
        "slippage": 0.1,
        "kill_switch_active": False,
        "recovery": ShadowRecovery(ShadowExecution()).admission(),
    }
    arguments.update(overrides)
    return evaluate_environment_gate(**arguments)


@pytest.mark.parametrize(
    "policy",
    (
        object(),
        BypassOperationalPolicy(
            max_quote_age_seconds=True,
            max_clock_skew_seconds=True,
        ),
    ),
    ids=("arbitrary-object", "validator-overriding-subclass"),
)
def test_operational_evaluator_requires_exact_owned_policy(policy):
    with pytest.raises(
        TypeError, match="operational policy must be exact OperationalPolicy"
    ):
        evaluate_operational_readiness(policy, snapshot())


@pytest.mark.parametrize(
    "policy",
    (
        object(),
        BypassBrokerSafetyPolicy(
            allowed_symbols="XAUUSD",
            max_spread=1.0,
            min_volume=0.01,
            max_volume=1.0,
            max_slippage=0.5,
        ),
    ),
    ids=("arbitrary-object", "validator-overriding-subclass"),
)
def test_broker_evaluator_requires_exact_owned_policy(policy):
    with pytest.raises(
        TypeError, match="broker policy must be exact BrokerSafetyPolicy"
    ):
        authorize_environment(
            policy,
            symbol="XAUUSD",
            spread=0.2,
            volume=0.03,
            slippage=0.1,
            connected=True,
            trading_enabled=True,
        )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        (
            "operational_policy",
            object(),
            "safety evaluation error: operational policy must be exact OperationalPolicy",
        ),
        (
            "broker_policy",
            object(),
            "safety evaluation error: broker policy must be exact BrokerSafetyPolicy",
        ),
    ),
)
def test_environment_gate_converts_wrong_policy_objects_to_issued_denials(
    field, value, reason,
):
    decision = environment_gate(**{field: value})

    assert decision.allowed is False
    assert decision.reasons == (reason,)
    assert is_gate_issued(decision) is True


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        (
            {
                "operational_policy": BypassOperationalPolicy(
                    max_quote_age_seconds=True,
                    max_clock_skew_seconds=True,
                ),
            },
            "safety evaluation error: operational policy must be exact OperationalPolicy",
        ),
        (
            {
                "broker_policy": BypassBrokerSafetyPolicy(
                    allowed_symbols="XAUUSD",
                    max_spread=1.0,
                    min_volume=0.01,
                    max_volume=1.0,
                    max_slippage=0.5,
                ),
                "symbol": "XAU",
            },
            "safety evaluation error: broker policy must be exact BrokerSafetyPolicy",
        ),
    ),
    ids=("operational-validator", "broker-validator"),
)
def test_validator_overrides_cannot_reopen_environment_authorization(
    overrides, reason,
):
    decision = environment_gate(**overrides)

    assert decision.allowed is False
    assert decision.reasons == (reason,)
    assert is_gate_issued(decision) is True


def test_exact_policy_objects_retain_the_authorized_control_path():
    decision = environment_gate()

    assert decision.allowed is True
    assert decision.reasons == ()
    assert is_gate_issued(decision) is True
