"""Single fail-closed admission firewall for strategy-level pre-trade validation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from core.setup_quality import SetupQualityInput, score_setup
from market.data_integrity import OHLCBar, validate_bars
from risk.news_firewall import NewsEvent, NewsFirewallPolicy


@dataclass(frozen=True)
class AdmissionFirewallResult:
    allowed: bool
    reason: str
    setup_score: int = 0


def validate_trade_admission(
    bars: Sequence[OHLCBar],
    setup: SetupQualityInput,
    timestamp: datetime,
    news_events: Iterable[NewsEvent] = (),
    currencies: Iterable[str] = (),
    news_policy: NewsFirewallPolicy = NewsFirewallPolicy(),
    min_setup_score: int = 70,
) -> AdmissionFirewallResult:
    """Apply data, setup-quality and news gates before any execution decision."""
    if isinstance(min_setup_score, bool) or not 0 <= min_setup_score <= 100:
        return AdmissionFirewallResult(False, "invalid minimum setup score")
    try:
        validate_bars(bars)
        quality = score_setup(setup)
        if quality.score < min_setup_score:
            return AdmissionFirewallResult(False, "setup quality below admission threshold", quality.score)
        if news_policy.blocked(timestamp, news_events, currencies):
            return AdmissionFirewallResult(False, "high-impact news firewall active", quality.score)
    except (TypeError, ValueError, RuntimeError) as exc:
        return AdmissionFirewallResult(False, "admission firewall rejected input: " + str(exc))
    return AdmissionFirewallResult(True, "all pre-trade firewall checks passed", quality.score)
