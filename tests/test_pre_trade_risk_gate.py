from datetime import date

from risk.daily_risk_ledger import DailyRiskLedger
from risk.pre_trade_risk_gate import evaluate_risk
from risk.risk_state import RiskState, RiskStateMachine


def test_risk_gate_allows_when_armed_and_budget_available():
    ledger = DailyRiskLedger(1000.0, 0.05)
    state = RiskStateMachine()
    result = evaluate_risk(date(2026, 9, 12), 10.0, ledger, state)
    assert result.allowed
    assert result.remaining_loss == 50.0


def test_risk_gate_blocks_cooldown():
    ledger = DailyRiskLedger(1000.0, 0.05)
    state = RiskStateMachine()
    state.record_result(-1.0)
    result = evaluate_risk(date(2026, 9, 12), 1.0, ledger, state)
    assert not result.allowed
    assert result.reason == "risk state is COOLDOWN"


def test_risk_gate_blocks_when_budget_is_exhausted():
    ledger = DailyRiskLedger(1000.0, 0.05)
    ledger.record(date(2026, 9, 12), -50.0)
    state = RiskStateMachine()
    result = evaluate_risk(date(2026, 9, 12), 0.01, ledger, state)
    assert not result.allowed
    assert result.reason == "daily risk budget exhausted"


def test_risk_gate_rejects_invalid_modeled_loss():
    ledger = DailyRiskLedger(1000.0, 0.05)
    state = RiskStateMachine()
    result = evaluate_risk(date(2026, 9, 12), -1.0, ledger, state)
    assert not result.allowed
    assert result.reason == "invalid modeled loss"
