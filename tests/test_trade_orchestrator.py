import pytest

from core.robustness import RobustnessReport
from core.signal_pipeline import AdmissionDecision
from core.trade_orchestrator import TradeOrchestrator
from paper_trading.engine import PaperTradingEngine
from risk.risk_budget import RiskBudget


def admission(allowed=True):
    return AdmissionDecision(allowed=allowed, reason="ok" if allowed else "blocked")


def robustness(passed=True):
    return RobustnessReport(wfo=None, monte_carlo=None, passed=passed, failures=())


def fixed_sizing(symbol, risk_usd, sl_distance):
    assert symbol == "XAUUSD"
    assert risk_usd > 0
    assert sl_distance > 0
    return 0.5


def test_orchestrator_fails_closed_on_admission():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine, sizing=fixed_sizing)
    plan = orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 10, admission(False), robustness(True))
    assert plan is None
    assert engine.open_order is None


def test_orchestrator_fails_closed_on_robustness():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine, sizing=fixed_sizing)
    plan = orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 10, admission(True), robustness(False))
    assert plan is None
    assert engine.open_order is None


def test_orchestrator_rejects_invalid_risk_budget():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine, sizing=fixed_sizing)
    with pytest.raises(ValueError):
        orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 0, admission(True), robustness(True))


def test_orchestrator_builds_and_submits_deterministically():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine, sizing=fixed_sizing)
    plan = orchestrator.plan("XAUUSD", "LONG", 100, 99, 102, 10, admission(True), robustness(True))
    assert plan is not None
    assert plan.volume == 0.5
    assert orchestrator.submit_plan(plan, "M15 confirmed") is True
    assert engine.open_order == plan_to_order(plan, "M15 confirmed")


def plan_to_order(plan, reason):
    from paper_trading.engine import PaperOrder
    return PaperOrder(plan.symbol, plan.direction, plan.entry, plan.stop_loss, plan.take_profit, plan.volume, reason)


def test_account_budget_exhaustion_blocks_plan():
    engine = PaperTradingEngine(1000)
    orchestrator = TradeOrchestrator(engine, sizing=fixed_sizing)
    budget = RiskBudget(equity=1000, risk_pct=0.01, daily_loss=-50, daily_loss_limit_pct=0.05)
    assert orchestrator.plan_from_account(
        "XAUUSD", "LONG", 100, 99, 102, budget, admission(True), robustness(True)
    ) is None
