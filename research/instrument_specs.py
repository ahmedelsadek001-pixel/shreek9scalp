"""Explicit instrument assumptions for SHREEK research backtests."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ResearchInstrumentSpec:
    """Broker-neutral price-unit assumptions that must be explicit in research."""

    symbol: str
    pip_size: float
    price_decimals: int

    def validate(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not isfinite(float(self.pip_size)) or self.pip_size <= 0:
            raise ValueError("pip_size must be finite and positive")
        if type(self.price_decimals) is not int or not 0 <= self.price_decimals <= 10:
            raise ValueError("price_decimals must be an integer from 0 to 10")


# OW Markets XAUUSD research export uses two decimal price precision. The
# Breakout + Retest legacy thresholds are expressed in 0.10 price-unit pips
# (20-40 pips = 2.0-4.0 USD consolidation range), so this assumption is kept
# explicit rather than embedded in the signal detector.
XAUUSD_RESEARCH_SPEC = ResearchInstrumentSpec(
    symbol="XAUUSD",
    pip_size=0.10,
    price_decimals=2,
)
XAUUSD_RESEARCH_SPEC.validate()
