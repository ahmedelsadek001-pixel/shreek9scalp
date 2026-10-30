"""Unified pre-trade integration gate for SHREEK V5.1.

The gate composes existing fail-closed controls without granting execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from core.admission_firewall import validate_trade_admission
from core.setup_quality import SetupQualityInput
from risk.news_firewall import NewsEvent, NewsFirewallPolicy


@dataclass(frozen=True)
class IntegrationDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_pre_trade(
    bars: Sequence[object],
    setup: SetupQualityInput,
    *,
    timestamp: datetime,
    setup_min_score: int,
    news_events: Sequence[NewsEvent] = (),
    currencies: Sequence[str] = (),
    news_policy: NewsFirewallPolicy = NewsFirewallPolicy(),
) -> IntegrationDecision:
    """Run the deterministic admission chain; any failed prerequisite blocks."""
    admission = validate_trade_admission(
        bars,
        setup,
        timestamp,
        news_events=news_events,
        currencies=currencies,
        news_policy=news_policy,
        min_setup_score=setup_min_score,
    )
    if not admission.allowed:
        return IntegrationDecision(False, (admission.reason,))
    return IntegrationDecision(True, ())
