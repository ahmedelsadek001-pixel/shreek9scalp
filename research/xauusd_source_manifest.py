"""Validated, broker-neutral XAUUSD source and cost manifest.

The manifest is research metadata only. It has no account, credential,
network, terminal, or order-routing authority. Round-turn commission is
converted to the per-execution value expected by the backtest engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from math import isclose, isfinite
from typing import Sequence

from core.backtest_engine import CostModel
from research.breakout_retest import ResearchBar


def _finite_non_negative(value: object, name: str) -> float:
    if type(value) not in (int, float) or not isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return float(value)


@dataclass(frozen=True)
class XAUUSDSourceManifest:
    """Explicit metadata required before broker-cost research is reproducible."""

    broker: str
    server: str
    symbol: str
    timezone_offset_minutes: int
    digits: int
    point_size: float
    contract_size: float
    minimum_volume: float
    volume_step: float
    observed_spread_points: float
    round_turn_commission_per_lot: float
    slippage_points: float

    def validate(self) -> None:
        for value, name in ((self.broker, "broker"), (self.server, "server"), (self.symbol, "symbol")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.symbol.strip().upper() != "XAUUSD":
            raise ValueError("symbol must be XAUUSD")
        if type(self.timezone_offset_minutes) is not int or not -14 * 60 <= self.timezone_offset_minutes <= 14 * 60:
            raise ValueError("timezone_offset_minutes is outside the valid timezone range")
        if type(self.digits) is not int or not 0 <= self.digits <= 10:
            raise ValueError("digits must be an integer between zero and ten")
        for value, name in (
            (self.point_size, "point_size"),
            (self.contract_size, "contract_size"),
            (self.minimum_volume, "minimum_volume"),
            (self.volume_step, "volume_step"),
        ):
            if type(value) not in (int, float) or not isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be a finite positive number")
        expected_point = 10.0 ** (-self.digits)
        if not isclose(float(self.point_size), expected_point, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("point_size does not match digits")
        if self.minimum_volume > self.volume_step:
            raise ValueError("minimum_volume must not exceed volume_step")
        _finite_non_negative(self.observed_spread_points, "observed_spread_points")
        _finite_non_negative(self.round_turn_commission_per_lot, "round_turn_commission_per_lot")
        _finite_non_negative(self.slippage_points, "slippage_points")

    @property
    def timezone(self) -> tzinfo:
        self.validate()
        return timezone(timedelta(minutes=self.timezone_offset_minutes))

    @property
    def spread_price(self) -> float:
        self.validate()
        return float(self.observed_spread_points) * float(self.point_size)

    @property
    def slippage_price(self) -> float:
        self.validate()
        return float(self.slippage_points) * float(self.point_size)

    @property
    def point_value(self) -> float:
        """Quote-currency value of a one-price-unit move per lot."""
        self.validate()
        return float(self.contract_size)

    @property
    def commission_per_execution(self) -> float:
        self.validate()
        return float(self.round_turn_commission_per_lot) / 2.0

    def to_cost_model(self) -> CostModel:
        """Return the engine cost model without enabling any execution path."""
        return CostModel(
            slippage=self.slippage_price,
            point_value=self.point_value,
            commission_per_volume=self.commission_per_execution,
        )

    def to_breakout_retest_config(self, *, pip_size: float, volume: float = 1.0):
        """Build a research backtest config with manifest-derived economics."""
        self.validate()
        from core.enums import Timeframe
        from research.backtest_breakout_retest import BreakoutRetestBacktestConfig

        return BreakoutRetestBacktestConfig(
            pip_size=pip_size,
            volume=volume,
            spread=self.spread_price,
            slippage=self.slippage_price,
            point_value=self.point_value,
            commission_per_volume=self.commission_per_execution,
            timeframe=Timeframe.M5,
        )

    def validate_bars_timezone(self, bars: Sequence[ResearchBar]) -> None:
        """Reject a CSV whose aware timestamps disagree with the manifest."""
        self.validate()
        if not isinstance(bars, Sequence) or not bars:
            raise ValueError("bars must be a non-empty sequence")
        expected = self.timezone.utcoffset(None)
        for bar in bars:
            timestamp = bar.timestamp
            if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("manifest-bound bars must have timezone-aware timestamps")
            if timestamp.utcoffset() != expected:
                raise ValueError("bar timestamp offset does not match source manifest")
