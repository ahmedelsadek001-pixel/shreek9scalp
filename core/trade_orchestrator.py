"""End-to-end, fail-closed orchestration for SHREEK V5.1 paper trades.

The orchestrator composes existing components without moving their authority
boundaries: admission decides eligibility, robustness decides validation,
risk sizing determines volume, and the paper engine is the final execution
boundary. No broker or live execution is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional

from core.signal_pipeline import AdmissionDecision
from core.robustness import RobustnessReport
from journal.decision_journal import DecisionJournal, DecisionRecord
from paper_trading.engine import PaperOrder, PaperTradingEngine
from risk.position_sizing import compute_lot_size


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
    """Compose gates and paper execution into one deterministic decision path."""

    def __init__(self, paper_engine: PaperTradingEngine, journal: Optional[DecisionJournal] = None) -> None:
        self.paper_engine = paper_engine
        self.journal = journal

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
        """Build a trade plan only after all non-execution gates pass."""
        if not isinstance(admission, AdmissionDecision) or not admission.allowed:
            self._journal_reject(symbol, direction, "signal admission failed")
            return None
        if not isinstance(robustness, RobustnessReport) or not robustness.passed:
            self._journal_reject(symbol, direction, "robustness validation failed")
            return None
        if not isfinite(risk_budget) or risk_budget <= 0:
            raise ValueError("risk_budget must be positive and finite")
        self._validate_levels(symbol, direction, entry, stop_loss, take_profit)
        volume = compute_lot_size(symbol, risk_budget, abs(entry - stop_loss))
        if not isfinite(volume) or volume <= 0:
            self._journal_reject(symbol, direction, "position sizing failed")
            return None
        return TradePlan(symbol, direction, entry, stop_loss, take_profit, volume, risk_budget)

    def submit_plan(self, plan: TradePlan, reason: str = "") -> bool:
        """Submit a previously gated plan to paper execution."""
        order = PaperOrder(
            plan.symbol, plan.direction, plan.entry, plan.stop_loss,
            plan.take_profit, plan.volume, reason,
        )
        return self.paper_engine.submit(
            order,
            admitted=True,
            robustness_passed=True,
            max_risk_usd=plan.risk_budget,
        )
