"""End-to-end, fail-closed orchestration for SHREEK V5.1 paper trades."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable, Optional

from core.signal_pipeline import AdmissionDecision
from core.robustness import RobustnessReport
from journal.decision_journal import DecisionJournal, DecisionRecord
from paper_trading.engine import PaperOrder, PaperTradingEngine
from risk.position_sizing import compute_lot_size
from risk.risk_budget import RiskBudget

SizingFunction = Callable[[str, float, float], float]


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    volume: float
    risk_budget: float


class TradeOrchestrator:
    """Enforce the only supported path from validated signal to paper order."""

    def __init__(
        self,
        paper_engine: PaperTradingEngine,
        journal: Optional[DecisionJournal] = None,
        sizing: SizingFunction = compute_lot_size,
    ) -> None:
        self.paper_engine = paper_engine
        self.journal = journal
        self.sizing = sizing

    def _journal_reject(self, symbol: str, direction: str, reason: str) -> None:
        if self.journal is None:
            return
        self.journal.append(
            DecisionRecord.now(
                symbol, "ORCHESTRATOR_REJECT", direction, reason,
                fingerprint=None, score=None, setup_type=None, frame=None,
                entry=None, sl=None,
            )
        )

    @staticmethod
    def _validate_levels(symbol: str, direction: str, entry: float, stop_loss: float, take_profit: float) -> None:
        PaperOrder(symbol, direction, entry, stop_loss, take_profit, 1.0).validate()

    def plan(
        self,
        symbol: str,
        direction: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        risk_budget: float,
        admission: AdmissionDecision,
        robustness: RobustnessReport,
    ) -> Optional[TradePlan]:
        """Build a plan only after admission, robustness and risk checks pass."""
        if not isinstance(admission, AdmissionDecision) or not admission.allowed:
            self._journal_reject(symbol, direction, "signal admission failed")
            return None
        if not isinstance(robustness, RobustnessReport) or not robustness.passed:
            self._journal_reject(symbol, direction, "robustness validation failed")
            return None
        if not isfinite(risk_budget) or risk_budget <= 0:
            raise ValueError("risk_budget must be positive and finite")
        self._validate_levels(symbol, direction, entry, stop_loss, take_profit)
        volume = self.sizing(symbol, risk_budget, abs(entry - stop_loss))
        if not isfinite(float(volume)) or volume <= 0:
            self._journal_reject(symbol, direction, "position sizing failed")
            return None
        return TradePlan(symbol, direction, entry, stop_loss, take_profit, float(volume), risk_budget)

    def plan_from_account(
        self,
        symbol: str,
        direction: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        budget: RiskBudget,
        admission: AdmissionDecision,
        robustness: RobustnessReport,
    ) -> Optional[TradePlan]:
        """Derive per-trade risk from account state, then build the plan."""
        risk_budget = budget.amount
        if risk_budget <= 0:
            self._journal_reject(symbol, direction, "daily risk budget exhausted")
            return None
        return self.plan(
            symbol, direction, entry, stop_loss, take_profit,
            risk_budget, admission, robustness,
        )

    def submit_plan(self, plan: TradePlan, reason: str = "") -> bool:
        """Submit a previously gated plan to the deterministic paper engine."""
        order = PaperOrder(
            plan.symbol, plan.direction, plan.entry, plan.stop_loss,
            plan.take_profit, plan.volume, reason,
        )
        return self.paper_engine.submit(
            order, admitted=True, robustness_passed=True,
            max_risk_usd=plan.risk_budget,
        )
