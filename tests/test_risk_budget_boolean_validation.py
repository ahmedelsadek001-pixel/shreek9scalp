import pytest

from risk.risk_budget import RiskBudget


@pytest.mark.parametrize("field,value", [
    ("equity", True),
    ("equity", False),
    ("risk_pct", True),
    ("risk_pct", False),
    ("max_risk_amount", True),
])
def test_constructor_rejects_boolean_numeric_fields(field, value):
    kwargs = {"equity": 1000.0}
    kwargs[field] = value
    with pytest.raises((TypeError, ValueError)):
        RiskBudget(**kwargs)


@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("position", ["entry", "stop", "volume", "point_value"])
def test_modeled_loss_rejects_boolean_trade_values(value, position):
    args = {"entry": 100.0, "stop": 99.0, "volume": 1.0, "point_value": 1.0}
    args[position] = value
    with pytest.raises((TypeError, ValueError)):
        RiskBudget(1000.0).modeled_loss(**args)


@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("position", ["entry", "stop", "point_value"])
def test_size_for_stop_rejects_boolean_values(value, position):
    args = {"entry": 100.0, "stop": 99.0, "point_value": 1.0}
    args[position] = value
    with pytest.raises((TypeError, ValueError)):
        RiskBudget(1000.0).size_for_stop(**args)
