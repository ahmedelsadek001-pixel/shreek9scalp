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
    assert ledger.loss_used(day) == 30
    assert ledger.loss_remaining(day) == 20


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
    assert not ledger.can_open(day, -1)
    assert not ledger.can_open(day, float("nan"))
