"""Unified pre-trade integration gate for SHREEK V5.1.

The gate composes existing fail-closed controls without granting execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.admission_firewall import validate_trade_admission
from core.setup_quality import SetupQuality
from market.data_integrity import validate_bars
from risk.news_firewall import NewsEvent, NewsFirewallPolicy


@dataclass(frozen=True)
class IntegrationDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_pre_trade(
    bars: Sequence[object],
    setup: SetupQuality,
    *,
    setup_min_score: int,
    news_events: Sequence[NewsEvent],
    news_policy: NewsFirewallPolicy,
) -> IntegrationDecision:
    """Run the deterministic admission chain; any failed prerequisite blocks."""
    data = validate_bars(bars)
    if not data.valid:
        return IntegrationDecision(False, (f"data integrity: {data.reason}",))

    admission = validate_trade_admission(
        bars,
        setup,
        setup_min_score=setup_min_score,
        news_events=news_events,
        news_policy=news_policy,
    )
    if not admission.allowed:
        return IntegrationDecision(False, admission.reasons)
    return IntegrationDecision(True, ())
