from datetime import date

import pytest

from risk.daily_risk_ledger import DailyRiskLedger


def test_daily_loss_budget_uses_losses_only():
    ledger = DailyRiskLedger(1000, 0.05)
    day = date(2026, 9, 12)
    ledger.record(day, 20)
    assert ledger.loss_used(day) == 0
    assert ledger.loss_remaining(day) == 50
    ledger.record(day, -30)
    assert ledger.loss_used(day) == 10
    assert ledger.loss_remaining(day) == 40


def test_modeled_loss_cannot_exceed_remaining_budget():
    ledger = DailyRiskLedger(1000, 0.05)
    day = date(2026, 9, 12)
    ledger.record(day, -40)
    assert ledger.can_open(day, 10)
    assert not ledger.can_open(day, 11)
    with pytest.raises(RuntimeError):
        ledger.require_can_open(day, 11)


def test_invalid_modeled_loss_fails_closed():
    ledger = DailyRiskLedger(1000, 0.05)
    day = date(2026, 9, 12)
    for value in (-1, float("nan"), float("inf"), None, "bad", 10**10000):
        assert not ledger.can_open(day, value)


@pytest.mark.parametrize(
    "value",
    [None, "bad", float("nan"), float("inf"), 0, -1, 10**10000],
    ids=["none", "nonnumeric", "nan", "infinity", "zero", "negative", "huge-int"],
)
def test_invalid_pnl_is_rejected_without_mutating_ledger(value):
    ledger = DailyRiskLedger(1000, 0.05)
    day = date(2026, 9, 12)
    with pytest.raises(ValueError):
        ledger.record(day, value)
    assert ledger.realized(day) == 0


def test_overflowing_cumulative_pnl_is_rejected_without_mutation():
    ledger = DailyRiskLedger(1e308, 0.5)
    day = date(2026, 9, 12)
    ledger.record(day, 1e308)
    with pytest.raises(ValueError, match="cumulative"):
        ledger.record(day, 1e308)
    assert ledger.realized(day) == 1e308


def test_invalid_constructor_values_raise_value_error():
    for equity, pct in [(None, 0.05), ("bad", 0.05), (1e308, 1.0), (1000, float("nan"))]:
        with pytest.raises(ValueError):
            DailyRiskLedger(equity, pct)
