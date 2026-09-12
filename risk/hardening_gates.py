"""Adapters that expose V5.1 hardening policies through the existing gate API."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from core.setup_quality import SetupQualityInput, score_setup
from risk.news_firewall import NewsEvent, NewsFirewallPolicy
from risk.trade_gates import GateResult


def setup_quality_gate(setup: SetupQualityInput, minimum_score: int = 60) -> GateResult:
    """Convert deterministic setup quality into an execution gate."""
    if isinstance(minimum_score, bool) or not 0 <= minimum_score <= 100:
        return GateResult(False, "invalid setup-quality threshold")
    try:
        result = score_setup(setup)
    except (TypeError, ValueError, RuntimeError) as exc:
        return GateResult(False, "invalid setup quality: %s" % exc)
    if result.score < minimum_score or not result.tradable:
        return GateResult(False, "setup quality below execution threshold")
    return GateResult(True, "setup quality acceptable")


def news_firewall_gate(
    policy: NewsFirewallPolicy,
    timestamp: datetime,
    events: Iterable[NewsEvent],
    currencies: Iterable[str] = (),
) -> GateResult:
    """Convert the causal news firewall into a fail-closed execution gate."""
    try:
        blocked = policy.blocked(timestamp, events, currencies)
    except (TypeError, ValueError, RuntimeError) as exc:
        return GateResult(False, "invalid news-firewall state: %s" % exc)
    if blocked:
        return GateResult(False, "high-impact news firewall active")
    return GateResult(True, "news firewall clear")
