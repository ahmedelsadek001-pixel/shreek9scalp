from dataclasses import replace

import pytest

from core.robustness import RobustnessReport
from core.signal_pipeline import AdmissionDecision
from core.trade_orchestrator import TradeOrchestrator
from paper_trading.engine import PaperTradingEngine


class FakeSizing:
    pass


def admission(allowed=True):
    return AdmissionDecision(allowed=allowed, reason="ok" if allowed else "blocked")


def robustness(passed=True):
    return RobustnessReport(wfo=None, monte_carlo=None, passed=passed, failures=())


def test_orchestrator_fails_closed_on_admission():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine)
    plan = orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 10, admission(False), robustness(True), (1.0, -0.5))
    assert plan is None
    assert engine.open_order is None


def test_orchestrator_fails_closed_on_robustness():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine)
    plan = orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 10, admission(True), robustness(False), (1.0, -0.5))
    assert plan is None
    assert engine.open_order is None


def test_orchestrator_rejects_empty_validation_sequence():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine)
    plan = orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 10, admission(True), robustness(True), ())
    assert plan is None


def test_orchestrator_rejects_invalid_risk_budget():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine)
    with pytest.raises(ValueError):
        orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 0, admission(True), robustness(True), (1.0,))
