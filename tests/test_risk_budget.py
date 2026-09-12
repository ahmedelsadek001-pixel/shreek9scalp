from risk.risk_budget import RiskBudget


def test_risk_amount_uses_equity_percentage_and_cap():
    assert RiskBudget(10000, 0.01).risk_amount == 100
    assert RiskBudget(10000, 0.02, max_risk_amount=150).risk_amount == 150
    assert RiskBudget(10000, 0.02, max_risk_amount=100).risk_amount == 100


def test_modeled_loss_and_allowance():
    budget = RiskBudget(10000, 0.01)
    assert budget.modeled_loss(2500, 2490, 5) == 50
    assert budget.allows(2500, 2490, 10) is True
    assert budget.allows(2500, 2490, 10.0000001) is False


def test_size_for_stop_is_deterministic():
    budget = RiskBudget(10000, 0.01)
    assert budget.size_for_stop(2500, 2490) == 10
    assert budget.size_for_stop(2500, 2490, 2) == 5


def test_invalid_risk_inputs_fail_closed():
    for args in ((0, 0.01), (10000, 0), (10000, 1.1)):
        try:
            RiskBudget(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid budget must fail")

    budget = RiskBudget(10000, 0.01)
    for values in ((2500, 2500, 1), (2500, 2490, 0), (2500, 2490, 1, 0)):
        try:
            budget.modeled_loss(*values)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid trade risk inputs must fail")
