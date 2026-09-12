"""End-to-end deterministic paper-trade admission pipeline for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

    modeled_loss = abs(float(entry) - float(sl)) * float(volume)
    risk: RiskAdmission = evaluate_risk(timestamp.date(), modeled_loss, engine.ledger, engine.risk_state)
    if not risk.allowed:
        return PipelineDecision(False, "risk", risk.reason)

    engine.submit(PaperOrder(symbol, direction, entry, sl, volume, timestamp))
    return PipelineDecision(True, "paper_execution", "paper order accepted")
