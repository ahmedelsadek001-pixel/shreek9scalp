"""End-to-end deterministic paper-trade admission pipeline for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Sequence

from core.enums import Direction
from core.integration_gate import IntegrationDecision, evaluate_pre_trade
from core.setup_quality import SetupQualityInput
from paper_trading.engine import PaperOrder, PaperTradingEngine
from risk.news_firewall import NewsEvent, NewsFirewallPolicy
from risk.pre_trade_risk_gate import RiskAdmission, evaluate_risk


@dataclass(frozen=True)
class PipelineDecision:
    allowed: bool
    stage: str
    reason: str


def admit_and_submit_paper(
    engine: PaperTradingEngine,
    bars: Sequence[object],
    setup: SetupQualityInput,
    *,
    timestamp: datetime,
    symbol: str,
    direction: Direction,
    entry: float,
    sl: float,
    volume: float,
    setup_min_score: int,
    news_events: Sequence[NewsEvent] = (),
    currencies: Sequence[str] = (),
    news_policy: NewsFirewallPolicy = NewsFirewallPolicy(),
) -> PipelineDecision:
    """Require strategy admission and risk admission before paper submission."""
    if not isinstance(engine, PaperTradingEngine):
        return PipelineDecision(False, "order_validation", "paper engine required")
    if not isinstance(timestamp, datetime):
        return PipelineDecision(False, "order_validation", "timestamp must be a datetime")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return PipelineDecision(False, "order_validation", "timestamp must be timezone-aware")

    try:
        normalized_entry = float(entry)
        normalized_sl = float(sl)
        normalized_volume = float(volume)
    except (TypeError, ValueError, OverflowError):
        return PipelineDecision(False, "order_validation", "invalid order price or volume")

    if not all(math.isfinite(value) and value > 0 for value in (normalized_entry, normalized_sl, normalized_volume)):
        return PipelineDecision(False, "order_validation", "order price and volume must be finite and positive")
    if normalized_entry == normalized_sl:
        return PipelineDecision(False, "order_validation", "entry and stop loss must differ")
    if direction not in (Direction.BUY, Direction.SELL):
        return PipelineDecision(False, "order_validation", "direction must be BUY or SELL")
    if direction is Direction.BUY and normalized_sl >= normalized_entry:
        return PipelineDecision(False, "order_validation", "BUY stop must be below entry")
    if direction is Direction.SELL and normalized_sl <= normalized_entry:
        return PipelineDecision(False, "order_validation", "SELL stop must be above entry")

    try:
        modeled_loss = engine.modeled_loss(normalized_entry, normalized_sl, normalized_volume)
    except ValueError:
        return PipelineDecision(False, "order_validation", "invalid modeled loss")

    admission: IntegrationDecision = evaluate_pre_trade(
        bars,
        setup,
        timestamp=timestamp,
        setup_min_score=setup_min_score,
        news_events=news_events,
        currencies=currencies,
        news_policy=news_policy,
    )
    if not admission.allowed:
        return PipelineDecision(False, "admission", "; ".join(admission.reasons))

    risk: RiskAdmission = evaluate_risk(timestamp.date(), modeled_loss, engine.ledger, engine.risk_state)
    if not risk.allowed:
        return PipelineDecision(False, "risk", risk.reason)

    engine.submit(PaperOrder(symbol, direction, normalized_entry, normalized_sl, normalized_volume, timestamp))
    return PipelineDecision(True, "paper_execution", "paper order accepted")
