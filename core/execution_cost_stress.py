"""Execution-cost stress using explicit gross P&L and cost components.

This diagnostic scales spread and slippage costs independently while keeping
commission unchanged. It is intentionally separate from the legacy
net-outcome shock in core.risk_simulation and grants no certification.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


def _finite_number(value: object, name: str) -> float:
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{name} must contain finite real numbers")
    return float(value)


@dataclass(frozen=True)
class ExecutionCostStressResult:
    baseline_net_pnl: tuple[float, ...]
    stressed_net_pnl: tuple[float, ...]
    total_gross_pnl: float
    total_spread_cost: float
    total_slippage_cost: float
    total_commission: float
    total_baseline_net_pnl: float
    total_stressed_net_pnl: float
    spread_multiplier: float
    slippage_multiplier: float


def stress_execution_costs(
    gross_pnl: Sequence[float],
    spread_costs: Sequence[float],
    slippage_costs: Sequence[float],
    commissions: Sequence[float],
    *,
    spread_multiplier: float = 1.0,
    slippage_multiplier: float = 1.0,
) -> ExecutionCostStressResult:
    """Return per-trade net P&L after scaling explicit execution costs only.

    All four sequences must have identical non-zero cardinality. Costs must
    be non-negative. Commission is held constant; spread and slippage are
    independently multiplied. No assumptions are inferred from net P&L.
    """
    sequences = (gross_pnl, spread_costs, slippage_costs, commissions)
    if any(isinstance(values, (str, bytes)) for values in sequences):
        raise ValueError("trade P&L and cost components must be numeric sequences")
    try:
        lengths = tuple(len(values) for values in sequences)
    except TypeError as exc:
        raise ValueError("trade P&L and cost components must be sized sequences") from exc
    if not lengths[0] or len(set(lengths)) != 1:
        raise ValueError("gross P&L and cost component sequences must have equal non-zero length")

    spread_factor = _finite_number(spread_multiplier, "spread_multiplier")
    slippage_factor = _finite_number(slippage_multiplier, "slippage_multiplier")
    if spread_factor < 1.0 or slippage_factor < 1.0:
        raise ValueError("cost multipliers must be finite numbers >= 1")

    gross_values = tuple(_finite_number(value, "gross_pnl") for value in gross_pnl)
    spread_values = tuple(_finite_number(value, "spread_costs") for value in spread_costs)
    slippage_values = tuple(_finite_number(value, "slippage_costs") for value in slippage_costs)
    commission_values = tuple(_finite_number(value, "commissions") for value in commissions)
    if any(value < 0 for values in (spread_values, slippage_values, commission_values) for value in values):
        raise ValueError("execution cost components must be non-negative")

    baseline = []
    stressed = []
    for gross, spread, slippage, commission in zip(
        gross_values, spread_values, slippage_values, commission_values
    ):
        base = gross - spread - slippage - commission
        stress = gross - spread * spread_factor - slippage * slippage_factor - commission
        if not isfinite(base) or not isfinite(stress):
            raise ValueError("net P&L must remain finite after cost calculation")
        baseline.append(base)
        stressed.append(stress)

    totals = (
        sum(gross_values), sum(spread_values), sum(slippage_values),
        sum(commission_values), sum(baseline), sum(stressed),
    )
    if any(not isfinite(value) for value in totals):
        raise ValueError("aggregate execution-cost stress values must remain finite")
    return ExecutionCostStressResult(
        tuple(baseline), tuple(stressed), *totals, spread_factor, slippage_factor
    )
