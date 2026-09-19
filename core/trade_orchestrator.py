"""Unified fail-closed trade orchestration for SHREEK V5.1.

This module is the single deterministic coordination point between signal
admission, strategy/data admission, risk sizing, duplicate-signal protection,
and paper execution. It has no broker transport authority and never performs
network I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Callable, Sequence

from core.duplicate_guard import DuplicateSignalGuard, signal_fingerprint
from core.enums import Direction
from core.integration_gate import evaluate_pre_trade
from core.models import TradeSignal
from core.signal_pipeline import AdmissionDecision, admit_signal
from core.setup_quality import SetupQualityInput
from paper_trading.engine import PaperOrder, PaperTradingEngine
from risk.news_firewall import NewsEvent, NewsFirewallPolicy
from risk.risk_budget import RiskBudget
from risk.trade_gates import GateResult


@dataclass(frozen=True)
class OrchestrationDecision:
    allowed: bool
    stage: str
    reason: str
    volume: float = 0.0
    fingerprint: str = ""


class TradeOrchestrator:
    """Coordinate all pre-paper controls without granting live execution authority."""

    def __init__(self, engine: PaperTradingEngine, risk_budget: RiskBudget) -> None:
        if not isinstance(engine, PaperTradingEngine):
            raise TypeError("engine must be PaperTradingEngine")
        if not isinstance(risk_budget, RiskBudget):
            raise TypeError("risk_budget must be RiskBudget")
        self.engine = engine
        self.risk_budget = risk_budget
        self.duplicate_guard = DuplicateSignalGuard()

    def evaluate_and_submit(
        self,
        signal: TradeSignal | None,
        bars: Sequence[object],
        setup: SetupQualityInput,
        *,
        timestamp: datetime,
        symbol: str,
        setup_min_score: int,
        point_value: float = 1.0,
        volume: float | None = None,
        gates: Sequence[tuple[str, Callable[[], GateResult]]] = (),
        news_events: Sequence[NewsEvent] = (),
        currencies: Sequence[str] = (),
        news_policy: NewsFirewallPolicy = NewsFirewallPolicy(),
    ) -> OrchestrationDecision:
        """Run signal, strategy, risk, and idempotency admission before paper submission."""
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return OrchestrationDecision(False, "input", "timestamp must be timezone-aware")
        if not isinstance(symbol, str) or not symbol.strip():
            return OrchestrationDecision(False, "input", "symbol is required")
        if signal is None:
            return OrchestrationDecision(False, "signal", "signal unavailable")
        if not isinstance(signal, TradeSignal):
            return OrchestrationDecision(False, "signal", "signal must be TradeSignal")
        if signal.direction not in (Direction.BUY, Direction.SELL):
            return OrchestrationDecision(False, "signal", "direction is not executable")

        signal_admission: AdmissionDecision = admit_signal(signal, gates)
        if not signal_admission.allowed:
            return OrchestrationDecision(False, "signal", signal_admission.reason)

        strategy = evaluate_pre_trade(
            bars,
            setup,
            timestamp=timestamp,
            setup_min_score=setup_min_score,
            news_events=news_events,
            currencies=currencies,
            news_policy=news_policy,
        )
        if not strategy.allowed:
            return OrchestrationDecision(False, "admission", "; ".join(strategy.reasons))

        try:
            entry = float(signal.entry_price)
            stop = float(signal.sl_price)
            numeric_point_value = float(point_value)
        except (TypeError, ValueError, OverflowError):
            return OrchestrationDecision(False, "risk", "risk inputs must be numeric")
        if not all(isfinite(value) and value > 0 for value in (entry, stop, numeric_point_value)):
            return OrchestrationDecision(False, "risk", "invalid risk inputs")

        if volume is None:
            try:
                volume = self.risk_budget.size_for_stop(entry, stop, numeric_point_value)
            except (TypeError, ValueError, OverflowError):
                return OrchestrationDecision(False, "risk", "position sizing failed")
        else:
            try:
                volume = float(volume)
            except (TypeError, ValueError, OverflowError):
                return OrchestrationDecision(False, "risk", "volume must be numeric")

        try:
            volume = float(volume)
        except (TypeError, ValueError, OverflowError):
            return OrchestrationDecision(False, "risk", "position sizing returned a non-numeric volume")
        if not isfinite(volume) or volume <= 0:
            return OrchestrationDecision(False, "risk", "position volume must be positive and finite")
        if not self.risk_budget.allows(entry, stop, volume, numeric_point_value):
            return OrchestrationDecision(False, "risk", "risk budget exceeded", volume)

        try:
            fingerprint = signal_fingerprint(symbol, signal)
            duplicate = self.duplicate_guard.reserve(fingerprint)
        except (TypeError, ValueError, OverflowError) as exc:
            return OrchestrationDecision(False, "duplicate", str(exc), volume)
        if not duplicate.allowed:
            return OrchestrationDecision(False, "duplicate", duplicate.reason, volume, fingerprint)

        try:
            self.engine.submit(PaperOrder(symbol, signal.direction, entry, stop, volume, timestamp))
        except Exception as exc:
            # Always release the reservation when submission fails, including
            # unexpected adapter exceptions, so a failed attempt cannot poison retries.
            self.duplicate_guard.discard(fingerprint)
            return OrchestrationDecision(False, "paper_execution", str(exc), volume, fingerprint)
        return OrchestrationDecision(True, "paper_execution", "paper order accepted", volume, fingerprint)

    def release_signal(self, fingerprint: str) -> None:
        """Release an active signal identity after its lifecycle is complete."""
        self.duplicate_guard.discard(fingerprint)
