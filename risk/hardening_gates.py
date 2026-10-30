"""Adapters that expose V5.1 hardening policies through the existing gate API."""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Iterable

from core.setup_quality import SetupQualityInput, score_setup
from risk.news_firewall import NewsEvent, NewsFirewallPolicy
from risk.trade_gates import GateResult


def setup_quality_gate(setup: SetupQualityInput, minimum_score: int = 60) -> GateResult:
    """Convert deterministic setup quality into an execution gate."""
    if type(minimum_score) is not int or not 0 <= minimum_score <= 100:
        return GateResult(False, "invalid setup-quality threshold")
    if not isinstance(setup, SetupQualityInput):
        return GateResult(False, "invalid setup quality input")
    try:
        result = score_setup(setup)
    except (TypeError, ValueError, RuntimeError, OverflowError) as exc:
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
    if not isinstance(policy, NewsFirewallPolicy):
        return GateResult(False, "invalid news-firewall policy")
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        return GateResult(False, "invalid news-firewall timestamp")
    if isinstance(events, (str, bytes)) or isinstance(currencies, (str, bytes)):
        return GateResult(False, "invalid news-firewall collections")
    try:
        event_values = tuple(events)
        currency_values = tuple(currencies)
    except (TypeError, ValueError, RuntimeError, OverflowError):
        return GateResult(False, "invalid news-firewall collections")
    if any(not isinstance(event, NewsEvent) for event in event_values):
        return GateResult(False, "invalid news-firewall event")
    if any(type(currency) is not str or not currency.strip() for currency in currency_values):
        return GateResult(False, "invalid news-firewall currency")
    try:
        blocked = policy.blocked(timestamp, event_values, currency_values)
    except (TypeError, ValueError, RuntimeError, OverflowError) as exc:
        return GateResult(False, "invalid news-firewall state: %s" % exc)
    if blocked:
        return GateResult(False, "high-impact news firewall active")
    return GateResult(True, "news firewall clear")
