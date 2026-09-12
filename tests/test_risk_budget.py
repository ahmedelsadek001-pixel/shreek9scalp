import pytest

from risk.risk_budget import RiskBudget


def test_budget_is_minimum_of_trade_and_remaining_daily_risk():
    budget = RiskBudget(equity=1000, risk_pct=0.01, daily_loss=-5, daily_loss_limit_pct=0.05)
    assert budget.amount == pytest.approx(10)


def test_daily_limit_can_reduce_available_risk():
    budget = RiskBudget(equity=1000, risk_pct=0.04, daily_loss=-30, daily_loss_limit_pct=0.05)
    assert budget.amount == pytest.approx(20)


def test_exhausted_daily_limit_blocks_new_risk():
    budget = RiskBudget(equity=1000, risk_pct=0.01, daily_loss=-50, daily_loss_limit_pct=0.05)
    assert budget.amount == 0


def test_per_trade_risk_cannot_exceed_daily_limit():
    with pytest.raises(ValueError):
        RiskBudget(equity=1000, risk_pct=0.06, daily_loss_limit_pct=0.05).amount


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        RiskBudget(equity=0, risk_pct=0.01).amount
    with pytest.raises(ValueError):
        RiskBudget(equity=1000, risk_pct=0.01, daily_loss_limit_pct=0).amount
